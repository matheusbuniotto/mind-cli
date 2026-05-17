---
name: simplify-ai-architecture
description: Review, refactor, and design AI-assisted codebases to reduce token inflation, context dilution, and unnecessary abstraction. Use when the user asks about architecture for projects where LLMs or Claude Code are primary collaborators, or when a codebase shows over-layering, one-implementation interfaces, mapper chains, or excessive file-touch radius.
---

# Simplify AI Architecture

---

## Core Problem This Skill Solves

Ritualistic layered architectures (Clean Architecture, Hexagonal, DDD Tactical patterns applied verbatim) were designed for human navigability. They impose a hidden tax in AI-assisted codebases:

- **Token inflation**: A single-field addition touches 10–18 files across layers.
- **Context dilution**: The LLM opens 7–13 files to reconstruct what a single vertical slice would show in 1–3.
- **Precision loss**: When dependencies are hidden behind interfaces resolved only at runtime, LLMs correctly identify needed files ~76% of the time (Navigation Paradox, 2026).
- **Abstraction hallucination**: LLMs are biased toward complex patterns (trained on blogs where Saga/Event Sourcing/Hexagonal are overrepresented); they suggest sophistication that doesn't fit the problem.

---

## The Rule Set

### 1. Strategic DDD first, tactical patterns never by default

Keep:
- **Bounded Contexts** — top-level domain folders (`billing/`, `orders/`, `identity/`). Smaller context windows = fewer irrelevant tokens fed to the LLM.
- **Ubiquitous Language** — code terms must match domain terms. When your prompt says "invoice" and the code says `InvoiceEntity`, precision degrades.

Drop (unless pain forces them):
- Repositories with interfaces when there's one implementation.
- Application service layer when it's a passthrough.
- DTO/mapper chains between layers.
- `domain/application/infra` folder triads inside each bounded context.

### 2. Flat structure inside modules

```
billing/
├── create-invoice.ts        # entry + business logic + persistence
├── cancel-invoice.ts
└── billing.test.ts
```

Not:

```
billing/
├── domain/
│   ├── Invoice.ts
│   └── InvoiceRepository.ts   ← interface
├── application/
│   └── CreateInvoiceUseCase.ts
├── infrastructure/
│   └── PrismaInvoiceRepository.ts
└── interfaces/
    └── InvoiceController.ts
```

Three files solving what eighteen tried to solve. The LLM reads all three in one context load.

### 3. Encapsulation yes, inversion of dependency only when real pain

- Hide Prisma/ORM behind a module boundary — the rest of the system must not import Prisma directly. That's encapsulation.
- Do NOT add an interface unless you have (or imminently plan to have) two concrete implementations that need to be swapped at runtime.

```typescript
// Good — encapsulated, no interface tax
// billing/db.ts (internal, never imported outside billing/)
import { prisma } from '../shared/db'
export const findInvoice = (id: string) => prisma.invoice.findUnique({ where: { id } })

// billing/create-invoice.ts
import { findInvoice } from './db'   // stays inside the bounded context
```

### 4. Abstraction by pain (YAGNI enforced)

Before adding a layer, ask:
- **"Has this changed in the last 12 months?"** If no — don't abstract it.
- **"Do I have two concrete implementations today?"** If no — no interface.
- **"Does removing this file break any test?"** If no — delete it.

### 5. Vertical slices for features

A feature lives in one place. The LLM finds it in one context load.

```
features/
└── checkout/
    ├── checkout.handler.ts   # HTTP entry
    ├── checkout.logic.ts     # business rules (pure functions, easy to test)
    └── checkout.data.ts      # DB access
```

Tests live next to their slice, not in a parallel mirror tree.

---

## When to Apply This Skill

| Situation | Action |
|-----------|--------|
| Reviewing existing architecture for AI-readiness | Audit file-touch radius for common changes; flag anything requiring >5 files |
| Greenfield project setup | Start flat inside bounded context folders; no tactical DDD layers |
| LLM keeps hallucinating wrong types or missing files | Flatten the area it's struggling with; check for interface indirection |
| "Should I add a Repository interface here?" | Only if swap is imminent. Default: no. |
| PR adds a layer "for future flexibility" | Reject unless the future scenario is named and dated |

---

## Audit Checklist

Run this against any module before declaring it AI-ready:

- [ ] Adding a field touches ≤5 files
- [ ] The LLM can understand the feature by reading ≤3 files
- [ ] No interface with a single implementation
- [ ] No DTO that mirrors the domain object 1:1
- [ ] Bounded context terms match the product/domain language exactly
- [ ] Tests are co-located with the logic they test

---

## Anti-Patterns to Flag in Review

| Anti-pattern | Why it hurts AI | Fix |
|---|---|---|
| `IUserRepository` with one impl | Doubles file count, hides the impl | Delete the interface |
| `UserDTO` ↔ `UserDomain` mapper | 3 extra files for a passthrough | Use the domain type directly at the boundary |
| `application/services/` passthrough | LLM reads service + use case + handler for one operation | Merge into handler or logic file |
| Mirror test tree (`tests/unit/domain/…`) | LLM can't find tests alongside code | Co-locate test files |
| Generic `BaseEntity` with id/createdAt via inheritance | Inheritance chains confuse type inference | Compose or use plain fields |

---

## Language-Specific Notes

**TypeScript**: Prefer `type` over `interface` for data shapes (no accidental declaration merging). Barrel `index.ts` files are fine at bounded context boundaries; avoid them inside a slice.

**Python**: Module = bounded context. Avoid ABCs unless you have two concrete implementors today. `dataclass` over ORM model inheritance.

**Go**: No inheritance exists — you're already forced flat. Keep packages small (one concern per package). Interfaces are defined by the consumer, not the provider.

---

## References

- Waldemar Neto — *Clean Architecture na Era da IA* (2026)
- Navigation Paradox paper (2026) — LLM file-retrieval precision degrades with indirection
- Addy Osmani — *Abstraction Bloat* (Google Engineering)
- Eric Evans — *Domain-Driven Design* (strategic patterns only)
