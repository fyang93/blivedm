# -*- coding: utf-8 -*-
import asyncio
import http.cookies
from typing import *

import aiohttp

import blivedm
import blivedm.models.web as web_models
import blivedm.models.open_live as open_models

import os
import json
import threading
from datetime import datetime
from pysignalr.client import SignalRClient
from pysignalr.messages import CompletionMessage


HUB_URL = os.getenv('BLIVE_HUB_URL', '').rstrip('/')

# 直播间ID的取值看直播间URL
ROOM_ID = ''

# 这里填一个已登录账号的cookie的SESSDATA字段的值。不填也可以连接，但是收到弹幕的用户名会打码，UID会变成0
SESSDATA = ''

session: Optional[aiohttp.ClientSession] = None

# 在开放平台申请的开发者密钥
ACCESS_KEY_ID = ''
ACCESS_KEY_SECRET = ''
# 在开放平台创建的项目ID
APP_ID = 0
# 主播身份码
ROOM_OWNER_AUTH_CODE = ''

sr_client = None
client = None
STOPPED = False


async def sample():
    global client
    if client is not None:
        stop_client()
    init_session()
    room_id = int(ROOM_ID)
    client = blivedm.BLiveClient(room_id, session=session)
    await run_single_client()


async def open_live_sample():
    global client
    if client is not None:
        stop_client()
    client = blivedm.OpenLiveClient(
        access_key_id=ACCESS_KEY_ID,
        access_key_secret=ACCESS_KEY_SECRET,
        app_id=APP_ID,
        room_owner_auth_code=ROOM_OWNER_AUTH_CODE,
    )
    await run_single_client()


def init_session():
    cookies = http.cookies.SimpleCookie()
    cookies['SESSDATA'] = SESSDATA
    cookies['SESSDATA']['domain'] = 'bilibili.com'

    global session
    session = aiohttp.ClientSession()
    session.cookie_jar.update_cookies(cookies)


async def run_single_client():
    global client, STOPPED
    handler = MyHandler()
    client.set_handler(handler)
    client.start()
    STOPPED = False
    while not STOPPED:
        await asyncio.sleep(1)


async def stop_client():
    global client, session
    STOPPED = True
    await asyncio.sleep(1)
    if client is None:
        return
    try:
        await client.join()
    finally:
        await client.stop_and_close()
        if session is not None:
            session.close()
            session = None


class MyHandler(blivedm.BaseHandler):
    # # 演示如何添加自定义回调
    # _CMD_CALLBACK_DICT = blivedm.BaseHandler._CMD_CALLBACK_DICT.copy()
    #
    # # 入场消息回调
    # def __interact_word_callback(self, client: blivedm.BLiveClient, command: dict):
    #     print(f"[{client.room_id}] INTERACT_WORD: self_type={type(self).__name__}, room_id={client.room_id},"
    #           f" uname={command['data']['uname']}")
    # _CMD_CALLBACK_DICT['INTERACT_WORD'] = __interact_word_callback  # noqa

    def _on_heartbeat(self, client: blivedm.BLiveClient, message: web_models.HeartbeatMessage):
        print(f'心跳')
        send_danmaku('心跳')

    def _on_enter(self, client: blivedm.BLiveClient, data: web_models.UserInData):
        print(f' {data.uname} 进入了直播间')
        send_danmaku({
            'username': data.uname,
            'content': '进入了直播间',
        })

    def _on_danmaku(self, client: blivedm.BLiveClient, message: web_models.DanmakuMessage):
        print(f'[{client.room_id}] {message.uname}: {message.msg}')
        send_danmaku({
            'username': message.uname,
            'content': message.msg,
        })

    def _on_gift(self, client: blivedm.BLiveClient, message: web_models.GiftMessage):
        print(f'[{client.room_id}] {message.uname} 赠送{message.gift_name}x{message.num}'
              f' ({message.coin_type}瓜子x{message.total_coin})')
        send_danmaku({
            'username': message.uname,
            'content': f'赠送{message.gift_name}x{message.num} ({message.coin_type}瓜子x{message.total_coin})'
        })

    def _on_buy_guard(self, client: blivedm.BLiveClient, message: web_models.GuardBuyMessage):
        print(f'[{client.room_id}] {message.username} 购买{message.gift_name}')
        send_danmaku({
            'username': message.username,
            'content': f'赠送{message.gift_name}x{message.num} ({message.coin_type}瓜子x{message.total_coin})'
        })

    def _on_super_chat(self, client: blivedm.BLiveClient, message: web_models.SuperChatMessage):
        print(f'[{client.room_id}] 醒目留言 ¥{message.price} {message.uname}: {message.message}')
        send_danmaku({
            'username': message.uname,
            'content': f'醒目留言 ¥{message.price}: {message.message}'
        })

    def _on_open_live_danmaku(self, client: blivedm.OpenLiveClient, message: open_models.DanmakuMessage):
        print(f'[{message.room_id}] {message.uname}: {message.msg}')
        send_danmaku({
            'username': message.uname,
            'content': message.msg
        })

    def _on_open_live_gift(self, client: blivedm.OpenLiveClient, message: open_models.GiftMessage):
        coin_type = '金瓜子' if message.paid else '银瓜子'
        total_coin = message.price * message.gift_num
        print(f'[{message.room_id}] {message.uname} 赠送{message.gift_name}x{message.gift_num}'
              f' ({coin_type}x{total_coin})')
        send_danmaku({
            'username': message.uname,
            'content': f'赠送{message.gift_name}x{message.gift_num} ({coin_type}x{total_coin})'
        })

    def _on_open_live_buy_guard(self, client: blivedm.OpenLiveClient, message: open_models.GuardBuyMessage):
        print(f'[{message.room_id}] {message.user_info.uname} 购买 大航海等级={message.guard_level}')
        send_danmaku({
            'username': message.user_info.uname,
            'content': f'购买 大航海等级={message.guard_level}'
        })

    def _on_open_live_super_chat(
        self, client: blivedm.OpenLiveClient, message: open_models.SuperChatMessage
    ):
        print(f'[{message.room_id}] 醒目留言 ¥{message.rmb} {message.uname}: {message.message}')
        send_danmaku({
            'username': message.uname,
            'content': f'醒目留言 ¥{message.rmb}: {message.message}'
        })

    def _on_open_live_super_chat_delete(
        self, client: blivedm.OpenLiveClient, message: open_models.SuperChatDeleteMessage
    ):
        print(f'[{message.room_id}] 删除醒目留言 message_ids={message.message_ids}')

    def _on_open_live_like(self, client: blivedm.OpenLiveClient, message: open_models.LikeMessage):
        print(f'[{message.room_id}] {message.uname} 点赞')
        send_danmaku({
            'username': message.uname,
            'content': f'点赞'
        })


def send_danmaku(message):
    if isinstance(message, dict):
        message = json.dumps(message)
    if not isinstance(message, str):
        raise ValueError("message must be a string")
    try:
        asyncio.ensure_future(sr_client.send('SendDanmaku', [message]))
    except Exception as e:
        print(f"Failed to send message: {e}")

async def on_open() -> None:
    print('Connected to the server')

async def on_close() -> None:
    print('Disconnected from the server')

async def on_error(message: CompletionMessage) -> None:
    print(f'Received error: {message.error}')

async def on_start_web(messages: List[str]) -> None:
    global ROOM_ID, SESSDATA
    if not len(messages) == 1:
        return
    args = json.loads(messages[0])
    print(args)
    ROOM_ID = args['ROOM_ID']
    SESSDATA = args['SESSDATA']
    thread = threading.Thread(target=lambda: asyncio.run(sample()))
    thread.start()

async def on_start_open_live(messages: List[str]) -> None:
    global ACCESS_KEY_ID, ACCESS_KEY_SECRET, APP_ID, ROOM_OWNER_AUTH_CODE
    if not len(messages) == 1:
        return
    args = json.loads(messages[0])
    print(args)
    ACCESS_KEY_ID = args['ACCESS_KEY_ID']
    ACCESS_KEY_SECRET = args['ACCESS_KEY_SECRET']
    APP_ID = int(args['APP_ID'])
    ROOM_OWNER_AUTH_CODE = args['ROOM_OWNER_AUTH_CODE']
    thread = threading.Thread(target=lambda: asyncio.run(open_live_sample()))
    thread.start()

async def on_stop(args) -> None:
    print('stop')
    await stop_client()

async def main() -> None:
    global sr_client
    sr_client = SignalRClient(HUB_URL)
    sr_client.on_open(on_open)
    sr_client.on_close(on_close)
    sr_client.on_error(on_error)
    sr_client.on('StartWeb', on_start_web)
    sr_client.on('StartOpenLive', on_start_open_live)
    sr_client.on('Stop', on_stop)

    while True:
        try:
            await asyncio.gather(
                sr_client.run(),
            )
        except Exception as e:
            print(e)
            await asyncio.sleep(1)  

if __name__ == '__main__':
    asyncio.run(main())