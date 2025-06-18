# Docker版 aistudio-build-proxy
集成 无头浏览器 + Websocket代理

问题: 当前cookie导出方式导出的cookie时效较短.

## 使用方法:
1. 导出Cookie到项目`camoufox-py/cookies/`文件夹下

    (1) 安装该插件后[Cookie-Editor浏览器插件地址](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm)
    , 使用该插件导出自己的Cookie

    ![cookie-editor](/img/Cookie_Editor.png)
    
    (2) 粘贴到项目 `camoufox-py/cookies/[自己命名].json` 中

2. 修改浏览器配置`camoufox-py/config.yaml`

    (1) 在`camoufox-py`下, 将示例配置文件`config.yaml.example`, 重命名为 `config.yaml`, 然后修改`config.yaml`

    (2) 实例 1 的`cookie_file` 填入自己创建 cookie文件名

    (3) (可选项) `url` 默认为项目提供的AIStudio Build 链接(会连接本地5345的ws服务), 可修改为自己的

    (4) (可选项) proxy配置指定浏览器使用的代理服务器

3. 修改`docker-compose.yml`
    
    (1) 自己设置一个 `AUTH_API_KEY` , 最后自己调 gemini 时要使用该 apikey 调用, 不支持无 key
4. 在项目根目录, 通过`docker-compose.yml`启动Docker容器

    (1) 运行命令启动容器
    ```bash
    docker compose up -d
    ```

5. 等待一段时间后, 通过 http://127.0.0.1:5345 和 自己设置的`AUTH_API_KEY`使用.

## 日志查看
1. docker日志
```bash
docker logs [容器名]
```
2. 单独查看camoufox-py日志

    camoufox-py/logs/app.log

    且每次运行, logs下会有一张截图

