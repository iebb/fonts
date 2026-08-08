# iebb/fonts

An open catalog of original and adapted type families by iebb. Every family
owns its binaries, specimen, license, release notes, and validation tools in a
self-contained directory.

## Catalog

| Family | Scope | Variable axes | License |
| --- | --- | --- | --- |
| [Monaco GP Sans](./Monaco%20GP%20Sans/) | Latin, Filled + Outline | `wght` 100–900 | SIL OFL 1.1 |

The catalog website is published from `master` at
[iebb.github.io/fonts](https://iebb.github.io/fonts/).

## Repository convention

- `/<Font Name>/` contains the public specimen and release documentation.
- `/<Font Name>/fonts/` contains installable TTFs and browser-ready WOFF2s.
- `/<Font Name>/tools/` contains build and release validation utilities.
- The catalog root stays static and dependency-free so it can be served by
  GitHub Pages without a build step.
