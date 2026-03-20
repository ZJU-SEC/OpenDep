# Cargo Dependency Crawler

Crates.io officially maintains a [git repo](https://github.com/rust-lang/crates.io-index) that manages meta information about all packages, including dependencies. So all we need to do is clone the git repo locally to get efficient access to all the dependency information.

```bash
git clone git@github.com:rust-lang/crates.io-index.git
```