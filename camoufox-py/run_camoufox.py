import argparse
import json
import time
import os
import multiprocessing
import yaml  # 导入 YAML 库
import logging # 导入 logging 库
from playwright.sync_api import Page, expect 
from camoufox.sync_api import Camoufox

# --- 日志配置函数 ---
def setup_logging(log_file, prefix=None, level=logging.INFO):
    """
    配置日志记录器，使其输出到文件和控制台。
    支持一个可选的前缀，用于标识日志来源。

    每次调用都会重新配置处理器，以适应多进程环境。

    :param log_file: 日志文件的路径。
    :param prefix: (可选) 要添加到每条日志消息开头的字符串前缀。
    :param level: 日志级别。
    """
    logger = logging.getLogger('my_app_logger') 
    logger.setLevel(level)

    if logger.hasHandlers():
        logger.handlers.clear()

    base_format = '%(asctime)s - %(process)d - %(levelname)s - %(message)s'

    if prefix:
        log_format = f'%(asctime)s - %(process)d - %(levelname)s - {prefix} - %(message)s'
    else:
        log_format = base_format

    fh = logging.FileHandler(log_file)
    fh.setLevel(level)

    ch = logging.StreamHandler()
    ch.setLevel(level)

    formatter = logging.Formatter(log_format)
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)
    
    logger.propagate = False
    
    return logger

def handle_untrusted_dialog(page: Page, logger=None):
    """
    检查并处理 "Last modified by..." 的弹窗。
    如果弹窗出现，则点击 "OK" 按钮。
    """
    ok_button_locator = page.get_by_role("button", name="OK")

    try:
        if ok_button_locator.is_visible(timeout=10000): # 等待最多10秒
            logger.info(f"检测到弹窗，正在点击 'OK' 按钮...")
            
            ok_button_locator.click(force=True)
            logger.info(f"'OK' 按钮已点击。")
            expect(ok_button_locator).to_be_hidden(timeout=1000)
            logger.info(f"弹窗已确认关闭。")
        else:
            logger.info(f"在10秒内未检测到弹窗，继续执行...")
    except Exception as e:
        logger.info(f"检查弹窗时发生意外：{e}，将继续执行...")

def convert_cookie_editor_to_playwright(cookies_from_editor, logger=None):
    """
    将从 Cookie-Editor 插件导出的 cookie 列表转换为 Playwright 兼容的格式。
    """
    playwright_cookies = []
    allowed_keys = {'name', 'value', 'domain', 'path', 'expires', 'httpOnly', 'secure', 'sameSite'}

    for cookie in cookies_from_editor:
        pw_cookie = {}
        for key in ['name', 'value', 'domain', 'path', 'httpOnly', 'secure']:
            if key in cookie:
                pw_cookie[key] = cookie[key]
        if cookie.get('session', False):
            pw_cookie['expires'] = -1
        elif 'expirationDate' in cookie:
            if cookie['expirationDate'] is not None:
                pw_cookie['expires'] = int(cookie['expirationDate'])
            else:
                pw_cookie['expires'] = -1
        
        if 'sameSite' in cookie:
            same_site_value = str(cookie['sameSite']).lower()
            if same_site_value == 'no_restriction':
                pw_cookie['sameSite'] = 'None'
            elif same_site_value in ['lax', 'strict']:
                pw_cookie['sameSite'] = same_site_value.capitalize()
            elif same_site_value == 'unspecified':
                pw_cookie['sameSite'] = 'Lax'

        if all(key in pw_cookie for key in ['name', 'value', 'domain', 'path']):
            playwright_cookies.append(pw_cookie)
        else:
            logger.warning(f"跳过一个格式不完整的 cookie: {cookie}")
            
    return playwright_cookies

# --- 新增：处理成功导航后的逻辑 ---
def handle_successful_navigation(page: Page, logger, cookie_file_config):
    """
    在成功导航到目标页面后，执行后续操作（处理弹窗、截图、保持运行）。
    """
    logger.info("已成功到达目标页面。")
    page.click('body') # 给予页面焦点

    # 检查并处理 "Last modified by..." 的弹窗
    handle_untrusted_dialog(page, logger=logger)

    # 等待页面加载和渲染后截图
    logger.info("等待15秒以便页面完全渲染...")
    time.sleep(15)
    
    screenshot_dir = 'logs'
    screenshot_filename = os.path.join(screenshot_dir, f"screenshot_{cookie_file_config}_{int(time.time())}.png")
    try:
        page.screenshot(path=screenshot_filename, full_page=True)
        logger.info(f"已截屏到: {screenshot_filename}")
    except Exception as e:
        logger.error(f"截屏时出错: {e}")
        
    logger.info("实例将保持运行状态。每10秒点击一次页面以保持活动。")
    while True:
        try:
            page.click('body')
            time.sleep(10)
        except Exception as e:
            logger.error(f"在保持活动循环中出错: {e}")
            break # 如果页面关闭或出错，则退出循环

# --- 修改：主浏览器实例函数 ---
def run_browser_instance(config):
    """
    根据最终合并的配置，启动并管理一个单独的 Camoufox 浏览器实例。
    新增了对导航后URL的检查和处理逻辑。
    """
    cookie_file_config = config.get('cookie_file')
    cookie_file = os.path.join('cookies', cookie_file_config)
    logger = setup_logging(os.path.join('logs', 'app.log'), prefix=f"{cookie_file_config}")
    
    logger.info(f"尝试加载 Cookie 文件: {cookie_file}")

    expected_url = config.get('url')
    proxy = config.get('proxy')
    headless_setting = config.get('headless', 'virtual')
    # account_email = config.get('email') # 获取配置中的email

    if not cookie_file or not expected_url or not os.path.exists(cookie_file):
        logger.error(f"错误: 无效的配置或 Cookie 文件未找到 for {cookie_file}")
        return

    try:
        with open(cookie_file, 'r') as f:
            cookies_from_file = json.load(f)
    except Exception as e:
        logger.exception(f"读取或解析 {cookie_file} 时出错: {e}")
        return

    cookies = convert_cookie_editor_to_playwright(cookies_from_file, logger=logger)
    
    if str(headless_setting).lower() == 'true':
        headless_mode = True
    elif str(headless_setting).lower() == 'false':
        headless_mode = False
    else:
        headless_mode = 'virtual'

    launch_options = {"headless": headless_mode}
    if proxy:
        launch_options["proxy"] = {"server": proxy, "bypass": "localhost, 127.0.0.1"}
    launch_options["block_images"] = True
    
    screenshot_dir = 'logs'
    os.makedirs(screenshot_dir, exist_ok=True)

    try:
        with Camoufox(**launch_options) as browser:
            context = browser.new_context()
            context.add_cookies(cookies)
            logger.info(f"已为上下文添加 {len(cookies)} 个 Cookie。")
            page = context.new_page()
            
            logger.info(f"正在导航到: {expected_url}")
            # 使用 wait_until='domcontentloaded' 可以在页面结构加载后立即返回，不等所有资源
            page.goto(expected_url, wait_until='domcontentloaded', timeout=60000)

            # --- 新增步骤：在检查URL之前，先处理可能出现的初始弹窗 ---
            logger.info("页面初步加载完成，正在检查并处理初始弹窗（如Cookie横幅、欢迎页）...")
            
            # 弹窗处理后，页面可能刷新或状态改变，稍作等待并重新获取最终URL
            page.wait_for_timeout(2000) # 等待2秒确保DOM稳定
            # --- 关键逻辑：检查导航后的最终URL ---
            final_url = page.url
            logger.info(f"导航完成。最终URL为: {final_url}")


            # 场景1: 重定向到需要输入邮箱的登录页面
            if "accounts.google.com/v3/signin/identifier" in final_url:
                logger.error("检测到Google登录页面（需要输入邮箱）。Cookie已完全失效。")
                logger.error("请为此账户更新Cookie文件。正在终止此实例。")
                page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_identifier_page_{cookie_file_config}.png"))
                return # 终止
            # 场景2: 成功导航到目标页面或其子页面
            elif expected_url.split('?')[0] in final_url:
                logger.info("URL正确。现在最终验证页面内容以确认登录状态...")
                
                # 最终检查：即使URL正确，页面上是否还存在登录按钮？
                # 这是判断Cookie无效但未发生跳转的关键
                login_button_cn = page.get_by_role('button', name='登录')
                login_button_en = page.get_by_role('button', name='Login')
                
                if login_button_cn.is_visible(timeout=3000) or login_button_en.is_visible(timeout=3000):
                    logger.error("URL正确，但页面上仍显示'登录'按钮。这表明Cookie无效或会话已过期。")
                    page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_login_button_visible_{cookie_file_config}.png"))
                    return
                
                logger.info("页面内容验证通过，未发现登录按钮。确认已登录。")
                handle_successful_navigation(page, logger, cookie_file_config)

            # 场景3: 重定向到Google账户选择页面
            elif "accounts.google.com/v3/signin/accountchooser" in final_url:
                logger.warning("检测到Google账户选择页面。登录失败或Cookie已过期。")
                page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_chooser_click_failed_{cookie_file_config}.png"))
                return

            # 场景4: 其他意外的URL
            else:
                logger.error(f"导航到了一个意外的URL: {final_url}")
                logger.error("无法识别当前页面状态。正在终止此实例。")
                page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_unexpected_url_{cookie_file_config}.png"))
                return # 终止

    except KeyboardInterrupt:
        logger.info(f"正在关闭...")
    except Exception as e:
        logger.exception(f"运行 Camoufox 时发生严重错误: {e}")


def main():
    """
    主函数，读取 YAML 配置并为每个实例启动一个独立的浏览器进程。
    """
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    
    logger = setup_logging(os.path.join(log_dir, 'app.log'))

    logger.info("------------Camoufox 实例管理器开始启动------------")

    parser = argparse.ArgumentParser(description="通过 YAML 配置文件并发运行多个 Camoufox 实例。")
    parser.add_argument("config_file", help="YAML 配置文件的路径。")
    args = parser.parse_args()

    if not os.path.exists(args.config_file):
        logger.error(f"错误: 配置文件未找到 at {args.config_file}")
        return

    try:
        with open(args.config_file, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.exception(f"读取或解析 YAML 配置文件时出错: {e}")
        return

    global_settings = config.get('global_settings', {})
    instance_profiles = config.get('instances', [])

    if not instance_profiles:
        logger.error("错误: 在配置文件中没有找到 'instances' 列表。")
        return

    processes = []
    for profile in instance_profiles:
        final_config = global_settings.copy()
        final_config.update(profile)

        if 'cookie_file' not in final_config or 'url' not in final_config:
            logger.warning(f"警告: 跳过一个无效的配置项 (缺少 cookie_file 或 url): {profile}")
            continue
            
        process = multiprocessing.Process(target=run_browser_instance, args=(final_config,))
        processes.append(process)
        process.start()

    logger.info(f"已成功启动 {len(processes)} 个浏览器实例。按 Ctrl+C 终止所有实例。")

    try:
        for process in processes:
            process.join()
    except KeyboardInterrupt:
        logger.info("捕获到 Ctrl+C, 正在终止所有子进程...")
        for process in processes:
            process.terminate()
            process.join()
        logger.info("所有进程已终止。")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()