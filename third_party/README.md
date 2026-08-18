# 第三方组件

## DocuBrowser（GPL-3.0）

目录 `DocuBrowser/` 由 `scripts/setup_docubrowser.py` 自动克隆自：

https://github.com/linuxrebel/DocuBrowser

易知通过 `lib/docubrowser_bridge.py` 以外部进程方式调用，不修改其源码。许可见 `DocuBrowser/LICENSE`。

首次启动易知时会自动执行 setup；也可手动：

```powershell
cd Myknowledge
python scripts/setup_docubrowser.py
```
