# Security

## Reporting a vulnerability

Please don't open a public issue. Report it privately instead: the repo's **Security**
tab → **Report a vulnerability**. Only maintainers see the report, and the fix can land
before the details are public.

Useful to include: what's affected (the kit, or an app it generates), how to reproduce
it, and the impact. Please leave out real keys or personal data.

## Scope

- **The kit:** the renderer, skills, hooks, selftest and CI in this repo.
- **What it generates:** the template's auth, row-level security, API scoping, secret
  handling, CI workflows and git/agent hooks. A flaw here affects every app built with
  the kit, so these reports matter most.

Bugs in an app you built *on* the kit, outside the template's code, belong in that app's
own repo.

## Supported versions

Fixes go to `main`. There are no backport branches yet.
