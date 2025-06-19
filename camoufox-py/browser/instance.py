from utils.logger import setup_logging
from utils.cookie_handler import convert_cookie_editor_to_playwright
from browser.navigation import handle_successful_navigation
import os
import json
from camoufox.sync_api import Camoufox

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