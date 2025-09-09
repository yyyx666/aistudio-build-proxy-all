#!/bin/bash
if [ ! -z "$CONFIG" ]; then
	echo $CONFIG > /app/config.yaml
	echo "载入config.yaml"
fi

if [ ! -z "$COOKIE" ]; then
	echo $COOKIE > /app/cookies/user1_cookie.json
	echo "载入user1_cookie"
fi

if [ -n "$CONFIG_URL" ]; then
    # 使用curl下载
    curl -fsSL "$CONFIG_URL" -o /app/config.yaml
	echo "载入config.yaml"
else

if [ -n "$COOKIE_URL" ]; then
    # 使用curl下载
    curl -fsSL "$CONFIG_URL" -o /app/cookies/user1_cookie.json
	echo "载入user1_cookie"
else


/usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
