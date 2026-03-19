# Hermès Color Mapper (MVP)

一个可部署到 GitHub Pages 的小工具：
- 输入任意语种颜色名（中/英/日/法/别名）
- 返回多语颜色名
- 展示样本商品中的 **包型** 与 **金具**
- 数据源：`https://ginzacelia.com`

## 目录

- `scripts/fetch_ginzacelia.py`：抓取并生成数据
- `data/color_aliases.json`：人工维护的多语颜色映射（可持续扩充）
- `docs/index.html`：静态网页（GitHub Pages）
- `docs/data/colors.json`：生成后的数据库

## 本地更新数据

```bash
python3 scripts/fetch_ginzacelia.py
```

## 部署到 GitHub Pages

1. 新建 GitHub 仓库并 push 本项目
2. GitHub → Settings → Pages
3. Source 选择 **Deploy from a branch**
4. Branch 选择 `main`，folder 选择 `/docs`
5. 保存后等待部署完成

## 说明

- 目前以站点商品标题自动抽取颜色，可能存在少量误识别。
- 建议你按工作常用色持续补充 `data/color_aliases.json`，查询体验会明显提升。
- 后续扩展 2/3（CSV 导入导出、编辑后台）时不需要推翻现在的结构。