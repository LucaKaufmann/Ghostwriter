# Contributing to Ghostwriter

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

### Ghostwriter Backend (Python)

```bash
cd ghostwriter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

### Ghostwriter Frontend (SvelteKit)

```bash
cd ghostwriter/frontend
npm install
npm run dev
```

### Android (Epilogue App)

Requirements: JDK 17, Android SDK (API 33+)

```bash
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
./gradlew assembleDebug
./gradlew test
```

### iOS (Epilogue App)

Requirements: Xcode 17+, Tuist, iOS 18.0+

```bash
cd EpilogueIOS
make setup       # Builds XCFramework + generates Xcode project
tuist build
```

## Making Changes

1. Fork the repository and create a feature branch.
2. Keep changes focused — one feature or fix per PR.
3. Follow existing code style and patterns.
4. Add tests for new functionality where applicable.
5. Run relevant checks before submitting:
   - Backend: `cd ghostwriter && pytest`
   - Frontend: `cd ghostwriter/frontend && npm run check`
   - Android: `./gradlew test && ./gradlew lint`

## Commit Messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new feed import option
fix: resolve EPUB generation crash on empty articles
chore: update dependencies
docs: clarify Docker setup instructions
```

## Pull Requests

- Keep the title short and in Conventional Commits format.
- Include a summary of what changed and why.
- Note any testing you performed.
- Include screenshots for UI changes (Android, iOS, or web).

## Reporting Issues

Open an issue on GitHub with:
- Steps to reproduce
- Expected vs. actual behavior
- Platform and version info (Android/iOS/backend)

## License

By contributing, you agree that your contributions will be licensed under the [GPL 3.0 License](LICENSE).
