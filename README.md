# 图片/文件接收、发送模块

本项目用于接受图片和文件信息，然后发送到 WX 客户端为目所编制。拟定可接受形式为

- [x] `http/https` 的图片链接
- [x] `base64` 后的图片
- [x] `multipart-formdata` 的文件
- [ ] `image` 的文件
  - [ ] `png gif` 等

# Usage

1. 在目录下复制 `config.example.ini`，放置 `config.ini` 文件
2. 启动应用，将在 34567 端口启动服务。
