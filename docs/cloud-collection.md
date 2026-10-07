# Collection while the computer is off

The GitHub Actions workflow at `.github/workflows/collect-melting.yml` is scheduled daily for 10:00 Asia/Seoul. It requires this project on the GitHub repository's default branch and an online PostgreSQL `DATABASE_URL` secret. The current local database at `127.0.0.1` cannot be reached from a GitHub runner.

## Activate

1. Create an online PostgreSQL database. The connection string must allow external connections and require TLS. Neon is one option: <https://neon.com/>. Do not paste the connection string into chat or commit it to the repository.
2. Put this project at the root of the intended GitHub repository's default branch. Keep `.env`, `.venv`, and local data out of Git.
3. In the repository, open **Settings → Secrets and variables → Actions → New repository secret**. Name it `DATABASE_URL` and paste the online PostgreSQL connection string as its value.
4. Open **Actions → Collect Melting ranking → Run workflow** once. Confirm that table creation, profile registration, collection, and validation all succeed and that 50 ranks were saved.
5. Point the desktop app at the same online database if you want cloud-collected rankings in its screen. Plan any migration of existing local history before switching the desktop database URL.
6. After a successful cloud run, keep the local Codex collection automation paused to avoid duplicate 10:00 snapshots.

GitHub scheduled workflows run from the default branch and may start late or be dropped under load, especially at the top of the hour. Check the Actions run history regularly. The workflow also supports manual runs.

References: [GitHub schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), [GitHub repository secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).
