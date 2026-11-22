# SprintFlow — Jira Clone (Agile Sprint & Issue Tracking SaaS)

Multi-tenant issue/bug tracking platformu: workspace-lər, layihələr, Kanban sprint board,
rol-based təhlükəsizlik, audit trail və plan limitləri.

**Stack:** Quart (async Python) · SQLAlchemy 2.0 async + SQLite · Vanilla JS SPA

## 🚀 Başlanğıc

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed.py                  # demo data (istəyə bağlı)
hypercorn app.main:app --reload --bind 127.0.0.1:5000
# və ya: quart --app app.main:app --debug run
```

Brauzerdə aç: **http://127.0.0.1:5000**

### Demo hesablar (seed.py ilə)

| Email | Şifrə | İzah |
|---|---|---|
| `sarah@acme.dev` | `password123` | Acme Inc owner (WEB layihəsi) |
| `john@acme.dev` | `password123` | Acme Inc member |
| `demo@full.dev` | `password123` | "Quota Demo" workspace — 50 ticket dolu, 51-ci upgrade modalı göstərir |

## 📋 Tələblərə uyğunluq

### Task 1.1 — Multi-Tenant Workspace & Project API
- ✅ Sequential issue key: `UPDATE issue_counters ... RETURNING count` — **tək SQL ifadəsi, atomic**, paralel request-lərdə race condition yoxdur (WEB-1, WEB-2, ...)
- ✅ Yalnız workspace member-ləri ticket görə/dəyişə bilər (`require_member` hər endpoint-də)
- ✅ Rollar: `owner / admin / member` — invite, upgrade, layihə silmə yalnız admin+

### Task 1.2 — Interactive Kanban & Sprint Board
- ✅ 4 sütun: Backlog · In Progress · In Review · Done
- ✅ Drag-and-drop + **optimistic UI** (kart dərhal köçür, API rədd edilərsə geri qayıdır, 409 konfliktdə toast + refresh)
- ✅ Real-time axtarış (300ms debounce) + filter: məsul şəxs, prioritet, açar söz

### Task 1.3 — Ticket Detail, Activity Feed & Plan Quotas
- ✅ Markdown redaktoru (Write/Preview tab-ları, marked.js + DOMPurify XSS-ə qarşı) + şərhlər
- ✅ Audit trail: *"Sarah moved issue to In Review"*, *"Sarah assigned issue to John"* hər dəyişiklikdə `activities` cədvəlinə yazılır
- ✅ Free tier: **maks 1 layihə, 50 ticket** — 51-ci ticket-də **402 quota_exceeded** + upgrade modalı (Pro-ya keçid endpoint-i işləkdir: `POST /api/workspaces/<id>/upgrade`)

### Edge Case-lər
- ✅ **Concurrent updates:** hər issue-da `version` (optimistic locking). İstifadəçi köhnə versiya göndərərsə → `409 stale_version` + server versiyası. Status update `UPDATE ... WHERE id AND version` ilə atomic təsdiqlənir.
- ✅ **Project deletion safety:** aktiv (DONE olmayan) ticket-lər varkən `409 has_active_issues`; `?force=1` ilə **soft delete** (`deleted_at`) — ticket-lər saxlanılır, API-də gizlədilir.

## 🗂 Struktur

```
jira-clone/
├── app/
│   ├── main.py            # Quart app, blueprint qeydiyyatı, static
│   ├── db.py              # async engine, db_session (commit/rollback), PRAGMAlar
│   ├── models.py          # 8 cədvəl: users, workspaces, workspace_members,
│   │                      #   projects, issue_counters, issues, comments, activities, api_tokens
│   ├── auth.py            # PBKDF2 hash, token auth, require_member
│   ├── quotas.py          # Free tier limitləri (1 layihə / 50 ticket)
│   ├── serializers.py     # to_dict + workspace_user_map
│   ├── routers/
│   │   ├── auth_routes.py     # register / login / me / logout
│   │   ├── workspaces.py      # CRUD, invite, members, upgrade
│   │   ├── projects.py        # CRUD + soft delete + quota
│   │   └── issues.py          # issues CRUD, comments, activity, filters
│   └── static/              # SPA: index.html, app.js, style.css
├── seed.py
├── requirements.txt
└── run.py
```

## 🔌 API xülasəsi

| Metod | Yol | İzah |
|---|---|---|
| POST | `/api/auth/register` · `/api/auth/login` | token qaytarır (`Bearer`) |
| GET/POST | `/api/workspaces` | siyahı / yarat (owner olursan) |
| POST | `/api/workspaces/<id>/invite` | admin+, email ilə |
| POST | `/api/workspaces/<id>/upgrade` | owner — free→pro |
| GET/POST | `/api/workspaces/<id>/projects` | POST free tier-də 402 |
| PATCH/DELETE | `/api/projects/<id>` | DELETE soft delete (`?force=1`) |
| GET/POST | `/api/projects/<id>/issues` | `?q=&status=&priority=&assignee_id=` |
| PATCH | `/api/issues/<id>` | body-da mütləq `version` (409 = stale) |
| GET/POST | `/api/issues/<id>/comments` | |
| GET | `/api/issues/<id>/activity` | audit trail |

**Error kodları:** `402 quota_exceeded` · `403` non-member · `409 stale_version` · `409 has_active_issues`

