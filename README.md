# 谷歌改区服务 · 客户资料收集表

客户打开公网链接填表（邮箱、当前地区、目标地区、用途、联系方式、淘宝订单号、备注），
店主在 `/admin` 登录后查看全部提交、标记已处理、删除。

**设计红线：不收集密码。** 页面明确提示客户：密码不要填，登录只在谷歌官方页面由客户本人输入。

## 部署（Railway）
- 环境变量 `INTAKE_DB=/data/intake.db`，并挂 Volume 到 `/data`（重启不丢数据）
- 首次打开 `/admin` 设置管理员口令（至少 6 位），谁先设谁是管理员，设之前不要外传链接

## 本地运行
```
INTAKE_DB=./intake.db PORT=8080 python3 app.py
# 客户页 http://localhost:8080/  店主后台 http://localhost:8080/admin
```
