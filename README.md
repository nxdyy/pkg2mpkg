# pkg2mpkg - Wallpaper Engine PKG 转 MPKG 工具

将 Wallpaper Engine 桌面版的 `.pkg` 壁纸文件转换为手机版可用的 `.mpkg` 格式，保留音频和全部内容。

## 背景

Wallpaper Engine 的桌面版和手机版使用不同的包格式：

| | 桌面版 (PKG) | 手机版 (MPKG) |
|--|-------------|--------------|
| Magic 标识 | `PKGV0024` | `PKGM0020` |
| 纹理格式 | DXT5/DXT1 (GPU硬件压缩) | ETC2/ASTC (移动端GPU压缩) |
| 着色器 | 桌面端版本 | 移动端适配版本 |
| 元数据 | 不含 project.json/preview.gif | 包含 |

两种格式的容器结构完全相同，区别在于 Magic 标识、纹理压缩格式和部分文件内容。

## 功能

- 将 PKG 格式转换为 MPKG 格式（替换 Magic 标识）
- **保留音频文件**（.mp3/.flac/.ogg）
- 保留 scene.json 中的音频引用配置
- 自动将 DXT 纹理替换为移动端 ETC2/ASTC 格式
- 自动替换着色器为移动端适配版本
- 从参考 MPKG 中提取 project.json 和 preview.gif
- 正确重建条目表和偏移量

## 用法

### 转换

```bash
python pkg2mpkg.py <input.pkg> <reference.mpkg> [output.mpkg]
```

**参数：**
- `input.pkg` - 桌面版 PKG 文件
- `reference.mpkg` - **同一壁纸**的手机版 MPKG 文件（用于提取移动端纹理、着色器和元数据）
- `output.mpkg` - 输出文件路径（可选，默认为 `input_converted.mpkg`）

**示例：**

```bash
# 基本转换
python pkg2mpkg.py 2944773634pc.pkg 2944773634.mpkg

# 指定输出路径
python pkg2mpkg.py 2944773634pc.pkg 2944773634.mpkg output.mpkg
```

### 分析

查看 PKG/MPKG 文件的内部结构：

```bash
python pkg2mpkg.py <file.pkg|file.mpkg> --analyze
```

## 转换策略

| 文件类型 | 来源 | 说明 |
|---------|------|------|
| `project.json` | 参考 MPKG | 移动端必需的元数据 |
| `preview.gif` | 参考 MPKG | 壁纸预览图 |
| `.tex` 纹理 | 参考 MPKG | PC用DXT格式，移动端用ETC2/ASTC格式，必须替换 |
| `.frag` / `.vert` 着色器 | 参考 MPKG | 移动端有适配版本 |
| `scene.json` | **PKG 原版** | 保留音频引用等配置 |
| 音频文件 (.mp3/.flac/.ogg) | **PKG 原版** | 完整保留 |
| 其他文件 | **PKG 原版** | 完整保留 |

## 纹理格式说明

PC版和移动端使用不同的 GPU 纹理压缩格式：

| 格式 ID | 名称 | 平台 |
|---------|------|------|
| 0 | RGBA8888 | 通用（无压缩） |
| 4 | DXT5 | PC |
| 7 | DXT1 | PC |
| 5 | ETC2/ASTC | 移动端 |

移动端 GPU 不支持 DXT 格式，直接使用 PC 版纹理会导致显示异常（如背景缺失）。因此必须使用参考 MPKG 中的移动端格式纹理。

## 注意事项

1. **参考 MPKG 必须是同一壁纸**：`reference.mpkg` 应该是你要转换的壁纸的手机版文件，这样纹理、着色器和元数据才能正确匹配。

2. **音频播放**：手机版原版 Wallpaper Engine 不播放嵌入音频，音频可视化效果使用系统音频。如需播放嵌入音频，需要修改手机版客户端。

3. **文件大小**：转换后的文件会比官方 MPKG 大，因为保留了原始音频文件。

## 依赖

- Python 3.6+
- 无第三方依赖，仅使用标准库

## 文件格式参考

PKG/MPKG 容器结构：

```
[int32 magic长度][magic字符串]          # Magic: "PKGV0024" 或 "PKGM0020"
[int32 条目数量]
[int32 路径长度][路径字符串][int32偏移][int32大小]  × N个条目
[数据区：所有文件数据连续存放]
```

TEX 纹理文件结构：

```
[null-terminated "TEXV0005"]
[null-terminated "TEXI0001"]
[int32 format][int32 flags]
[int32 texWidth][int32 texHeight]
[int32 imgWidth][int32 imgHeight]
[int32 unkInt0]
[TEXB容器 + mipmap数据]
```
