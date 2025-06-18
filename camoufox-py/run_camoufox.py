import argparse
import json
import time
import os
import multiprocessing
import yaml  # 导入 YAML 库
import logging # 导入 logging 库

from camoufox.sync_api import Camoufox

# --- 日志配置函数 ---
def setup_logging(log_file, level=logging.INFO):
    """
    配置日志记录器，使其输出到文件和控制台。
    每个进程（包括主进程和子进程）都会调用此函数。
    """
    # 获取或创建日志记录器
    logger = logging.getLogger(__name__)
    logger.setLevel(level)

    # 避免重复添加处理器，特别是在多进程中 fork 模式下可能继承父进程的处理器
    # 对于Windows/macOS的spawn模式，这不是必需的，但有益于兼容性
    if not logger.handlers:
        # 创建文件处理器
        fh = logging.FileHandler(log_file)
        fh.setLevel(level)

        # 创建控制台处理器
        ch = logging.StreamHandler()
        ch.setLevel(level)

        # 定义日志格式
        # %(process)d 会自动获取当前进程的PID
        formatter = logging.Formatter('%(asctime)s - %(process)d - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        # 将处理器添加到日志记录器
        logger.addHandler(fh)
        logger.addHandler(ch)
    
    return logger

def sanitize_cookies(cookies):
    """清理 cookie 以使其与 Playwright/Camoufox 兼容。"""
    sanitized = []
    allowed_keys = {'name', 'value', 'domain', 'path', 'expires', 'httpOnly', 'secure', 'sameSite'}
    for cookie in cookies:
        new_cookie = {}
        for key, value in cookie.items():
            if key == 'expirationDate':
                new_cookie['expires'] = value
                continue
            if key == 'sameSite':
                # 'No_Restriction' 在某些上下文中等同于 'None'
                if value is None or str(value).lower() == 'no_restriction':
                    new_cookie['sameSite'] = 'None'
                elif str(value).lower() in ['lax', 'strict', 'none']:
                    new_cookie['sameSite'] = str(value).capitalize()
                else:
                    # 对于 Camoufox 不支持的值，默认设为 'None' 或根据需要处理
                    new_cookie['sameSite'] = 'None' 
                continue
            new_cookie[key] = value
        final_cookie = {k: v for k, v in new_cookie.items() if k in allowed_keys}
        sanitized.append(final_cookie)
    return sanitized

def run_browser_instance(config):
    """
    根据最终合并的配置，启动并管理一个单独的 Camoufox 浏览器实例。
    """
    # 为当前子进程设置日志
    logger = setup_logging(os.path.join('logs', 'app.log'))

    # 在cookies/文件夹下查找
    cookie_file = os.path.join('cookies', config.get('cookie_file'))
    logger.info(f"尝试加载 Cookie 文件: {cookie_file}") # 使用 logger.info 代替 print

    url = config.get('url')
    proxy = config.get('proxy')
    headless_setting = config.get('headless', 'virtual') # 默认为 'virtual'

    pid = os.getpid()
    logger.info(f"正在为 {cookie_file} 启动实例...") # 使用 logger.info 代替 print

    if not cookie_file or not url or not os.path.exists(cookie_file):
        logger.error(f"错误: 无效的配置或 Cookie 文件未找到 for {cookie_file}") # 使用 logger.error 代替 print
        return

    try:
        with open(cookie_file, 'r') as f:
            cookies_from_file = json.load(f)
    except Exception as e:
        logger.exception(f"读取或解析 {cookie_file} 时出错: {e}") # 使用 logger.exception 代替 print，它会打印 traceback
        return

    cookies = sanitize_cookies(cookies_from_file)
    logger.debug(f"已加载并清理的 Cookies: {cookies}") # 可以使用 logger.debug 打印详细信息，但默认级别不会显示

    # 将 headless 字符串/布尔值转换为 Camoufox 需要的类型
    if str(headless_setting).lower() == 'true':
        headless_mode = True
    elif str(headless_setting).lower() == 'false':
        headless_mode = False
    else:
        headless_mode = 'virtual'

    launch_options = {"headless": headless_mode}
    if proxy:
        launch_options["proxy"] = {
        "server": proxy,
        "bypass": "localhost, 127.0.0.1"
    }

    # 确保截图目录存在
    screenshot_dir = 'logs' # 截图保存到 'logs' 目录下
    os.makedirs(screenshot_dir, exist_ok=True) # exist_ok=True 避免目录已存在时报错

    try:
        with Camoufox(**launch_options) as browser:
            context = browser.new_context(
                # storage_state=cookies_from_file,
                # record_har_path="logs/har_pid{}.har".format(pid),
            )
            context.add_cookies(cookies)
            logger.info(f"已为上下文添加 {len(cookies)} 个 Cookie。")
            page = context.new_page()
            
            logger.info(f"正在导航到: {url}") # 使用 logger.info 代替 print
            page.goto(url)
            logger.info(f"页面加载完成。实例将保持运行状态。") # 使用 logger.info 代替 print
            page.click('body')

            # 等待15s页面加载和渲染后截图
            time.sleep(15)
            screenshot_filename = os.path.join(screenshot_dir, f"screenshot_{cookie_file}_{int(time.time())}.png")
            try:
                page.screenshot(path=screenshot_filename,full_page=True)
                logger.info(f"已截屏到: {screenshot_filename}") # 使用 logger.info 代替 print
            except Exception as e:
                logger.error(f"截屏时出错: {e}") # 使用 logger.error 代替 print
                
            # time.sleep(120)
            # context.close() # 关闭上下文时会自动保存HAR文件
            # browser.close()
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info(f"正在关闭...") # 使用 logger.info 代替 print
    except Exception as e:
        logger.exception(f"运行 Camoufox 时发生错误: {e}") # 使用 logger.exception 代替 print，它会打印 traceback

def main():
    """
    主函数，读取 YAML 配置并为每个实例启动一个独立的浏览器进程。
    """
    # 确保 logs 目录存在
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    
    # 为主进程设置日志
    logger = setup_logging(os.path.join(log_dir, 'app.log'))

    parser = argparse.ArgumentParser(description="通过 YAML 配置文件并发运行多个 Camoufox 实例。")
    parser.add_argument("config_file", help="YAML 配置文件的路径。")
    args = parser.parse_args()

    if not os.path.exists(args.config_file):
        logger.error(f"错误: 配置文件未找到 at {args.config_file}") # 使用 logger.error 代替 print
        return

    try:
        with open(args.config_file, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.exception(f"读取或解析 YAML 配置文件时出错: {e}") # 使用 logger.exception 代替 print
        return

    global_settings = config.get('global_settings', {})
    instance_profiles = config.get('instances', [])

    if not instance_profiles:
        logger.error("错误: 在配置文件中没有找到 'instances' 列表。") # 使用 logger.error 代替 print
        return

    processes = []
    for profile in instance_profiles:
        # 合并配置：以全局设置为基础，用实例特定设置覆盖
        final_config = global_settings.copy()
        final_config.update(profile)

        if 'cookie_file' not in final_config or 'url' not in final_config:
            logger.warning(f"警告: 跳过一个无效的配置项 (缺少 cookie_file 或 url): {profile}") # 使用 logger.warning 代替 print
            continue
            
        process = multiprocessing.Process(target=run_browser_instance, args=(final_config,))
        processes.append(process)
        process.start()

    logger.info(f"已成功启动 {len(processes)} 个浏览器实例。按 Ctrl+C 终止所有实例。") # 使用 logger.info 代替 print

    try:
        for process in processes:
            process.join()
    except KeyboardInterrupt:
        logger.info("捕获到 Ctrl+C, 正在终止所有子进程...") # 使用 logger.info 代替 print
        for process in processes:
            process.terminate() # 尝试终止进程
            process.join()      # 等待进程完全关闭
        logger.info("所有进程已终止。") # 使用 logger.info 代替 print

if __name__ == "__main__":
    multiprocessing.freeze_support() # 对打包成可执行文件有好处
    main()