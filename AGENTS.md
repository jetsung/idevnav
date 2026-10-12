# Agent 工作指南 (AGENTS.md)

本文档记录了在本项目中由 AI Agent 执行常见任务时的标准化流程与规范。

---

## 站点收录与新增流程

当用户提供 URL 要求添加到导航时，按照以下标准化流程处理：

### 1. 栏目自动判定
- **已有栏目匹配**：若用户未明确说明添加到哪个栏目，Agent 应自动分析目标站点的类型、功能与定位，在 [data/navsites.yml](file://data/navsites.yml) 已有的 `taxonomy`（分类）与 `term`（子分类）中匹配最合适的已有归属。
- **避免随意创建新栏目**：优先收录到现存成熟的分类下，除非用户明确要求新建分组。

### 2. 元数据抓取与提炼
若用户未提供 `title`、`logo` 或 `description`，通过网络请求目标 URL 进行抓取：
- **Title（名称）**：提取网页的 `<title>` 或 `og:site_name`，去除冗余后缀（如 “- 官方网站”、“| 首页”），提炼为简洁的项目/产品名称；若用户指定则以用户指定为准。
- **Description（描述）**：提取 `<meta name="description">` 或 `og:description`，凝练为一句话简述（建议 10~30 字以内，风格与站内其他条目保持一致）。
- **网络代理**：若环境变量 `IS_CHINA=1`，遵循中国网络代理规则访问外网资源。

### 3. Logo 提取与命名规范
- **命名规范**：
  - 提取域名的二级域名并去除顶级后缀，添加 `.png` 作为文件名。
  - 示例：`https://github.com` $\rightarrow$ `github.png`；`https://www.aipromonow.com/` $\rightarrow$ `aipromonow.png`。
- **提取方式（Google 方式）**：
  - 参考 [deploy.sh](file://deploy.sh) 中的 Google Favicon 服务接口获取 48px 图标：
    - 默认 / 海外环境：
      ```bash
      https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=${URL_ENCODED}&size=48
      ```
    - 国内环境（`IS_CHINA=1`）：
      ```bash
      https://t3.gstatic.cn/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=${URL_ENCODED}&size=48
      ```
  - **备选与兜底**：若 Google 接口未能获取到满意的高清图标，可从目标站点的 `/favicon.ico`、`apple-touch-icon` 或页面 `<link rel="icon">` 抓取并转换为标准 48×48 PNG。
- **存放路径**：
  - 保存至 [static/assets/images/logos/](file://static/assets/images/logos/)，确保实际文件格式为 PNG。

### 4. 写入数据文件
在 [data/navsites.yml](file://data/navsites.yml) 对应的 `taxonomy` $\rightarrow$ `list` $\rightarrow$ `term` $\rightarrow$ `links` 下追加条目，格式如下：

```yaml
    - title: <站点名称>
      logo: <二级域名>.png
      favicon:
      url: <URL>
      description: <站点简述>
```

### 5. 构建与同步验证
1. **Hugo 构建检查**：
   运行 `hugo --buildDrafts`，确保 YAML 语法无误且页面构建正常。
2. **Linkding 书签同步**：
   若配置了 `LINKDING_API_TOKEN`，执行 Skill 脚本完成同步与标签继承：
   ```bash
   python3 .agents/skills/linkding-sync-prepper/scripts/sync.py --apply -y
   ```
