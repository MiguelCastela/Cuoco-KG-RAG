# Cuoco frontend (Vite + React)

The chat interface for Cuoco. See the [root README](../README.md) for the full
project overview and setup.

## Getting started

```bash
npm install
npm run dev        # starts Vite at http://localhost:5173
```

The UI calls the backend at `http://localhost:8000` (`POST /chat`, `POST /clear`).
Start the backend first (see the root README).

## Configuration

Copy `.env.example` to `.env` to change the dev proxy target:

```
VITE_BACKEND_URL=http://localhost:8000
```

## Build for production

```bash
npm run build
npm run preview    # optional local preview of the build
```

## Where things live

- `src/App.jsx` - top-level chat logic and backend calls
- `src/components/` - UI components
- `src/index.css`, `src/fonts.css` - styling
- `vite.config.js` - dev server and `/api` proxy target
