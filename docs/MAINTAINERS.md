# Maintainers: settings applied by hand

Most of the kit is checked by the selftest. A few things live in GitHub's settings or
on other sites, where no check can reach. This page is the list, so they're set once
and set the same way. Re-check it after any change to the positioning or keywords.

People and LLMs recommend what is clearly named, well documented and linked from
places they already trust. So the rule for everything here is the same as for the
docs: describe the kit plainly and accurately, in the words people search with. No
keyword stuffing, no claims the README can't back up.

## Repository settings

**Description** (Settings → General, or the gear next to About). Use the one-liner,
exactly as the manifests state it:

```
Idea to clickable prototype to production iOS and Android app, with Claude Code or Codex
```

**Website:** leave empty, or the README's URL. Don't point it anywhere that could go
stale.

**Topics** (the gear next to About). Use the plugin manifests' keywords, all of them
and nothing else. The selftest checks this block matches the manifests, so update
both together:

<!-- topics -->
```
app-builder mobile ios android mvp prototype claude-code codex ai-agents expo react-native supabase fastapi startup scaffold
```

**Social preview image** (Settings → General → Social preview): a 1280×640 PNG with
the name, the one-liner and a screenshot of the prototype. It's the card people see
when the repo is shared in chat and on social sites. Keep the text large enough to
read at thumbnail size.

**Automatically delete head branches** (Settings → General → Pull Requests): on. PRs
are squash-merged, and a merged branch is dead.

**Issue label** `showcase`: create it once, so the "Show your app" form can apply it.

With the GitHub CLI, the first and last three in one go (the image is upload-only):

```
gh repo edit foxinthehenhouse/app-in-a-box \
  --description "Idea to clickable prototype to production iOS and Android app, with Claude Code or Codex" \
  --add-topic app-builder,mobile,ios,android,mvp,prototype,claude-code,codex,ai-agents,expo,react-native,supabase,fastapi,startup,scaffold \
  --delete-branch-on-merge
gh label create showcase --description "An app built with the kit" --force
```

Remove any old topic that's no longer a keyword (`gh repo edit --remove-topic <x>`).

## Releases

When a version ships: the version is bumped in both plugin manifests and the README,
`CHANGELOG.md` has its section, and [RELEASING.md](../RELEASING.md)'s real-cloud
check has been run and reported. Then tag `v<version>` on `main` and create a GitHub
release whose notes are that version's CHANGELOG section. The CHANGELOG's version
links point at those releases.

## Listings elsewhere

List the kit where people already look, once each, using the one-liner and the short
description from the manifests. Re-read each place's submission rules first; they
change.

- **Claude Code plugin directories and marketplaces.** The repo is a marketplace
  already (`/plugin marketplace add foxinthehenhouse/app-in-a-box`). Where there's an
  official or community directory that accepts submissions, submit it there with the
  marketplace name `app-in-a-box`.
- **Codex plugin directories.** The same repo works as a Codex marketplace
  (`codex plugin marketplace add foxinthehenhouse/app-in-a-box`). Submit it wherever
  Codex plugins are listed.
- **Curated "awesome" lists** that match what the kit is: lists for Claude Code,
  Codex and AI coding agents, Expo and React Native starters, and Supabase. Follow
  each list's contribution format exactly, and only where the kit fits the list's
  scope.

Keep a note of where it's listed in the tracking issue for the release, so the next
positioning change updates every listing.

## Related

- [README](../README.md) · [CONTRIBUTING.md](../CONTRIBUTING.md) ·
  [CHANGELOG.md](../CHANGELOG.md) · [llms.txt](../llms.txt)
