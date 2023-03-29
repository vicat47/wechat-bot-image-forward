import base64
import configparser
import time
import imghdr
import os
import urllib

from io import BytesIO
from pathlib import Path, PureWindowsPath
from typing import Optional

import aiofiles
import aiohttp
import fsspec

from aiohttp import web
from attr import asdict, dataclass

config = configparser.ConfigParser()
config.read('config.ini', encoding="UTF-8")


if not os.path.exists('temp_file'):
    print('temp file is not exists, creating...')
    os.makedirs('temp_file')


LOCAL_FILE_PATH = config.get("image", "path")
WECHAT_HOST_BASE_PATH = config.get("image", "wechat_host_base_path")
HOST = config.get("wechat", "host")
IMAGE_API = config.get("wechat", "image_api")
FILE_API = config.get("wechat", "file_api")
IMAGE_TYPE = ['jpeg', 'png', 'gif']


fs = None
if bool(config.has_section("smb_server") and config.get("smb_server", "active")):
    print("smb active!")
    fs = fsspec.filesystem('smb',
                           host=config.get("smb_server", "address"),
                           username=config.get("smb_server", "username"),
                           password=config.get("smb_server", "password"), timeout=10)
    REMOTE_PATH = config.get("smb_server", "root_path")

if bool(config.has_section("webdav_server") and config.get("webdav_server", "active")):
    print("webdav active!")
    from webdav4.fsspec import WebdavFileSystem
    fs = WebdavFileSystem(config.get("webdav_server", "address"),
                          auth=(config.get("webdav_server", "username"),
                                config.get("webdav_server", "password")))
    REMOTE_PATH = config.get("webdav_server", "root_path")

if fs is None:
    print("no file protocol")
    exit(0)

app = web.Application()


def get_id():
    return str(int(time.time() * 1000))


@dataclass
class WechatMessage:
    id: str = get_id()
    type: int = 500
    roomid: str = 'null'
    wxid: str = ''
    content: str = 'null'
    nickname: str = 'null'
    ext: str = 'null'

    async def send_image(self):
        self.type = 500
        return await post(HOST + IMAGE_API, asdict(self))

    async def send_file(self):
        self.type = 5003
        return await post(HOST + FILE_API, asdict(self))


async def handle(request):
    name = request.match_info.get('name', "Anonymous")
    text = "Hello, " + name
    return web.Response(text=text)


def file_name_from_header(resp: aiohttp.ClientResponse) -> Optional[str]:
    disposition = resp.content_disposition
    if disposition is None:
        return None
    # return urllib.parse.unquote(disposition.filename)
    return disposition.filename


async def file_from_url(request):
    image_json: dict = await request.json()
    async with aiohttp.ClientSession() as session:
        async with session.get(image_json.get('url')) as resp:
            print(resp)
            file_name = file_name_from_header(resp)
            image_bytes = await resp.read()
    is_image = False
    if file_name is None:
        what = imghdr.what(BytesIO(image_bytes))
        if what and what in IMAGE_TYPE:
            is_image = True
        file_name = get_id() + '.' + (what if what is not None else '')
    file_path = Path(LOCAL_FILE_PATH) / file_name
    await write_byte_to_file(image_bytes, file_path)
    if fs is not None:
        fs.upload(str(file_path), f"{REMOTE_PATH}/{file_name}")
    if is_image:
        result = await WechatMessage(wxid=image_json.get("wxid"),
                                     content=str(PureWindowsPath(f'{WECHAT_HOST_BASE_PATH}/{file_name}'))).send_image()
    else:
        result = await WechatMessage(wxid=image_json.get("wxid"),
                                     content=str(PureWindowsPath(f'{WECHAT_HOST_BASE_PATH}/{file_name}'))).send_file()
    print(result)
    return web.json_response(result)


async def file_from_multipart(request):
    wxid = request.match_info['wxid']
    reader = await request.multipart()

    # /!\ Don't forget to validate your inputs /!\

    # reader.next() will `yield` the fields of your form

    field = await reader.next()
    filename = get_id() + '.' + field.filename.split('.')[-1]
    # You cannot rely on Content-Length if transfer is chunked.
    size = 0
    file_path = Path(LOCAL_FILE_PATH) / filename
    with open(os.path.join(LOCAL_FILE_PATH, filename), 'wb') as f:
        while True:
            chunk = await field.read_chunk()  # 8192 bytes by default.
            if not chunk:
                break
            size += len(chunk)
            f.write(chunk)
    what = imghdr.what(str(file_path))
    if fs is not None:
        fs.upload(str(file_path), f"{REMOTE_PATH}/{filename}")
    if what and what in IMAGE_TYPE:
        result = await WechatMessage(wxid=wxid,
                                     content=str(PureWindowsPath(f'{WECHAT_HOST_BASE_PATH}/{filename}'))).send_image()
    else:
        result = await WechatMessage(wxid=wxid,
                                     content=str(PureWindowsPath(f'{WECHAT_HOST_BASE_PATH}/{filename}'))).send_file()
    # return web.Response(text='{} sized of {} successfully stored'
    #                          ''.format(filename, size))
    print(result)
    return web.json_response(result)


async def file_from_base64(request):
    image_json: dict = await request.json()
    wxid = image_json.get('wxid')
    base64_str = image_json.get('data')
    file_type = image_json.get('type')
    file_name = image_json.get('name')
    if file_name is None:
        file_name = get_id() + '.' + file_type
    else:
        file_type = Path(file_name).suffix[1:]
    data = base64.b64decode(base64_str)
    file_path = Path(LOCAL_FILE_PATH) / file_name
    await write_byte_to_file(data, file_path)
    if fs is not None:
        fs.upload(str(file_path), f"{REMOTE_PATH}/{file_name}")
    if file_type in IMAGE_TYPE:
        result = await WechatMessage(wxid=wxid,
                                content=str(PureWindowsPath(f'{WECHAT_HOST_BASE_PATH}/{file_name}'))).send_image()
    else:
        result = await WechatMessage(wxid=wxid,
                                     content=str(PureWindowsPath(f'{WECHAT_HOST_BASE_PATH}/{file_name}'))).send_file()
    print(result)
    return web.json_response(result)


async def write_byte_to_file(image_bytes, file_path):
    async with aiofiles.open(file_path, mode='wb') as f:
        return await f.write(image_bytes)


async def post(url, json_data):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={'para': json_data}) as resp:
            return await resp.text()


app.add_routes([web.post('/url', file_from_url)])
app.add_routes([web.post('/multipart/{wxid}', file_from_multipart)])
app.add_routes([web.post('/base64', file_from_base64)])

app.add_routes([web.get('/', handle)])

if __name__ == '__main__':
    web.run_app(app, port=34567)
