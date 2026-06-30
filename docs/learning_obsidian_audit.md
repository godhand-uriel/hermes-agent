# Learning Obsidian Audit

Generated: 2026-06-30

## Vault access

- Resolved vault path: `/home/yuu/Sync/ObsidianVault`
- Access result: readable by Hermes from the engineering_lab profile.
- Markdown notes found: 24
- Notes with YAML/frontmatter: 20

Hermes resolved the vault from the configured Obsidian environment path. The fallback `~/Documents/Obsidian Vault` path does not exist on this host.

## Existing learning-related structure

No dedicated `Learning/` folder exists yet.

Current top-level folders:

- `Career Development/` — 2 notes
- `Research/` — 4 notes
- `Personal/` — 3 notes
- `Business Ventures/` — 7 notes
- `Finance/` — 3 notes
- `Assets/` — 1 note
- `Integrum Exousia Holdings/` — 3 notes
- root — 1 note

Learning-adjacent notes detected by keyword search:

- `Career Development/Career Development.md`
- `Career Development/First Job.md`
- `Personal/Reading.md`
- `Business Ventures/Engineering Brand/Engineering Brand.md`
- `Business Ventures/Engineering Brand/youtube content manger prompt.md`
- `Business Ventures/Artist Management/Artist Management Supplies.md`
- `Assets/HermesOS/prompts/HERMES OS — EXECUTIVE COMMAND CENTER v1.md`

## Keyword audit

Search terms requested and observed note counts:

- AWS: 3
- Azure: 1
- Microsoft Learn: 0
- Certification: 2
- Study: 4
- Career: 13
- Linux: 2
- Security+: 0
- Terraform: 2
- Notes: 10
- Daily: 3

Important interpretation: these are content hits, not verified progress records. Several hits are dashboard prompts or operating notes, so the sync engine logs them for review unless the note uses typed learning frontmatter.

## Existing YAML/frontmatter usage

Frontmatter is common, but it is mostly operating-note metadata rather than learning-progress metadata.

Observed tags include:

- `career`
- `employment`
- `operating-note`
- `dashboard`
- `research`
- `reading`
- `engineering-brand`
- `artist-management`
- `finance`

No existing note had the recommended `type: learning` frontmatter at audit time.

## Existing career/study/certification structure

- Career narrative/operating notes exist under `Career Development/`.
- Study-like references exist in `Career Development/Career Development.md`, `Personal/Reading.md`, and some business/brand notes.
- Certification names appear in dashboard prompt/reference content, but no verified personal progress note was found with typed learning fields.
- No reliable Microsoft Learn or AWS Skill Builder personal-progress API connection is configured.

## Sync decision

The sync engine now treats Obsidian as the connected source but only imports structured progress from clearly typed learning notes or explicit learning frontmatter.

Ambiguous notes are preserved in `learning_registry.json.manual_review` with evidence paths. This prevents Career Command from showing fabricated progress.

## Recommended Obsidian structure

Create notes under:

```text
Learning/
  AWS/
    AWS SAA.md
  Microsoft/
    AZ-900.md
  Linux/
  Security/
  Daily Study Log.md
```

Recommended frontmatter:

```yaml
---
type: learning
provider: AWS
certification: AWS Solutions Architect Associate
status: in_progress
progress: 15
last_studied: 2026-06-29
next_action: Complete VPC module
---
```

Do not require every note to be perfect. The importer parses clear fields and logs ambiguous fields for manual review.
