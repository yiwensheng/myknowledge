# 易知授权服务 · Linux 生产部署参考
# 用法：上传 license-server/ 到 /opt/yizhi-license-server 后执行

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/yizhi-license-server}"
PY="${APP_DIR}/.venv/bin/python"

echo "=== 易知 license-server 部署 ==="

if [ ! -f "${APP_DIR}/.env" ]; then
  echo "请先复制 .env.example 为 .env 并填写生产参数"
  exit 1
fi

cd "${APP_DIR}"
python3 -m venv .venv
"${APP_DIR}/.venv/bin/pip" install -r requirements.txt

echo "安装 systemd 单元（需 root）:"
echo "  sudo cp deploy/yizhi-license.service /etc/systemd/system/"
echo "  sudo sed -i 's|/opt/yizhi-license-server|${APP_DIR}|g' /etc/systemd/system/yizhi-license.service"
echo "  sudo systemctl daemon-reload && sudo systemctl enable --now yizhi-license"

echo "配置 Nginx: 见 deploy/nginx.conf.example"

"${PY}" -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:18888/health').read())" \
  || echo "服务未启动，请 systemctl start yizhi-license"

echo "验收: curl -s https://license.你的域名/health"
