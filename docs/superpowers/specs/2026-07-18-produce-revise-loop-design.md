# 写文章 · 草稿改稿闭环 Design

**日期：** 2026-07-18  
**状态：** 待用户审阅 spec  
**产品：** 易知 Myknowledge「写文章」面板

## 背景

当前「写文章」一次生成后正文只读展示，并可在生成时自动写入知识库。用户需要：**生成内容可继续打磨**——既可直接改正文，也可提要求让 LLM 改稿——直到主动确认再入库。

## 目标

- 生成后进入**草稿态**，不自动写知识库。
- 正文**所见即所得可编辑**；另支持「按要求让 LLM 改稿」。
- 用户点**确认定稿**后才写入知识库；之后可「继续修改」再回到草稿。
- 改稿默认**不重新 RAG**；可选勾选「改稿时重新参考知识库」。

## 非目标

- 多版本历史 / diff / 协作批注
- 段落级局部改稿指令（整篇改稿即可）
- 定稿即 `published`（仍存为 wiki `draft`，走现有整理流程）
- 播客体例单独的改稿协议（共用同一套逻辑）

## 已确认决策

| 项 | 选择 |
|----|------|
| 入库时机 | 仅「确认定稿」写入；生成阶段不写库 |
| 编辑方式 | 区内直接可编辑（WYSIWYG）+「改稿要求」栏 |
| 改稿检索 | 默认不 RAG；可选重 RAG（方案 C） |
| 实现路径 | 方案 2：草稿态 / 定稿态 + `revise` / `finalize` API |

## 交互流程

```
空闲 →「开始写」→ 生成中(流式) → 草稿
                                      ↓
                    手改正文 /「按要求修改」(可选重 RAG)
                                      ↓
                               「确认定稿」→ 已定稿
                                      ↓
                               「继续修改」→ 草稿
```

### 控件

- **移除**「生成后自动保存到知识库」勾选（行为固定）。
- **草稿工具条**（`draft` / `finalized` 可见）：改稿要求、勾选「改稿时重新参考知识库」、「按要求修改」、「确认定稿」。
- **已定稿**：主按钮变为「继续修改」，并显示已写入的 `wiki_page`。
- 「开始写」：按主题**全新生成**；若当前有未定稿内容，二次确认覆盖。
- 「按要求修改」：以**当前 Markdown 正文**为底稿；要求为空则禁用或 toast。
- Word / 播客：草稿与已定稿均可导出/合成（边改边用）。
- 现有「待人工确认」引用勾选：不替代改稿；首版优先保证编辑与改稿，确认条不阻塞定稿（可挂在预览增强层，不强绑 Toast 内嵌）。

### 并发与校验

- 流式生成 / 改稿进行中：禁用开始写、改稿、定稿。
- 定稿时正文为空或明显失败文案：拒绝定稿。

## 前端状态

内存会话（刷新可丢，可接受）：

| 字段 | 含义 |
|------|------|
| `phase` | `idle \| streaming \| draft \| finalized` |
| `markdown` | 正文真源（手改与改稿后写回） |
| `topic` / `genre` / `title` / `sources` | 元数据 |
| `wiki_page` | 定稿后才有；再次定稿时覆盖同页 |
| `revise_use_rag` | 是否改稿时重检索 |

编辑器：草稿态挂载现有 **Toast UI**（`YizhiRichEditor`），真源 Markdown；流式阶段可用只读 HTML，结束后再挂编辑器。

## API

### 既有 `POST /api/produce`、`/api/produce/stream`

- 前端默认 `save_to_wiki=false`。
- 响应不变：`content`、`content_html`、`sources` 等。

### 新增 `POST /api/produce/revise`（及可选 `/revise/stream`）

**入参：** `content`（当前 Markdown）、`instruction`、`topic`、`genre`、`use_rag`、可选 `scope_paths` / `folder_ids` / `brief`。

**行为：**

- `use_rag=false`：在既有文稿上按要求修改，提示不编造无依据新事实；不重新检索。
- `use_rag=true`：与 produce 同策略检索后，将片段与当前正文、改稿要求一并注入再改写。

**出参：** 与 produce 类似的 `content` / `content_html` / `sources`。  
**来源策略：** 无 RAG 时**保留**原 `sources`（可由前端合并）；有 RAG 时用**新** `sources`。

### 新增 `POST /api/produce/finalize`

**入参：** `content`、`topic`、`genre`，可选 `title` / `tags` / `wiki_page`（已有路径则更新同页）。

**行为：** `save_page(..., status="draft")`（新建或覆盖）+ 延迟/增量索引；返回 `wiki_page`。

## 提示词原则

- 改稿 system：在用户提供的当前文稿上修改；遵守输出体例；**不得编造**检索中不存在的事实（有 RAG 时仅依据注入片段；无 RAG 时不新增无依据的具体数据/引用）。
- 与全局客观写作规则一致时复用既有 produce system，另加「改稿」任务块即可。

## 验收标准

1. 「开始写」完成后不出现「已保存到知识库」，除非用户随后定稿。
2. 草稿态可直接改字，改后下载 Word 反映手改内容。
3. 填写改稿要求 →「按要求修改」后正文更新；不勾选重 RAG 时不发起新检索（可测：mock / 日志）。
4. 勾选重 RAG 后改稿，返回新 `sources` 可用。
5. 「确认定稿」写入 wiki 草稿页；「继续修改」后再定稿覆盖同一页（或明确的同一路径更新）。
6. 有未定稿内容时「开始写」有覆盖确认。

## 相关文件（预期）

- `electron/renderer/index.html`、`app.js`、`rich-editor.js`（挂载）
- `backend/server.py`（revise / finalize）
- `lib/llm.py`（produce_revise 等）
- 可选：`prompts/` 改稿说明片段
- `docs/更新记录.md`
