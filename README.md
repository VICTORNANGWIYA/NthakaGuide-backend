# NthakaGuide — Flask Backend

Standalone Python/Flask backend that replaces the three Supabase Edge Functions:
`recommend`, `rainfall`, and `chat`.

---

## Project Structure

```
nthakaguide-backend/
├── app.py                    # Flask app entry point
├── requirements.txt
├── .env.example              # Copy to .env and fill in values
│
├── data/
│   ├── crop_data.py          # Crop statistics + Malawi crop name map
│   ├── rainfall_data.py      # Met station data + district defaults
│   └── expert_knowledge.py   # Agricultural Q&A knowledge base + system prompt
│
├── utils/
│   └── algorithms.py         # All shared algorithms (EWMA, GNB, fertilizer logic)
│
└── routes/
    ├── recommend.py          # POST /api/recommend
    ├── rainfall.py           # POST /api/rainfall
    └── chat.py               # POST /api/chat
```

---

## Setup

```bash
cd nthakaguide-backend

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set your LOVABLE_API_KEY
```

---

## Running the Server

**Development:**
```bash
python app.py
# Server starts at http://localhost:5000
```

**Production (with gunicorn):**
```bash
gunicorn "app:create_app()" --bind 0.0.0.0:5000 --workers 4
```

---

## API Endpoints

### `GET /api/health`
Health check.
```json
{ "status": "ok", "service": "NthakaGuide API" }
```

---

### `POST /api/recommend`
Full soil analysis — ML crop prediction + fertilizer plan.

**Request body:**
```json
{
  "nitrogen":      77,
  "phosphorus":    48,
  "potassium":     20,
  "ph":            6.2,
  "moisture":      65,
  "temperature":   22,
  "organicMatter": 1.8,
  "districtName":  "Zomba"
}
```

**Response:** Full `Recommendation` object with `crops`, `fertilizers`, `forecastedRainfall`, `soilAlerts`, `fertilizerAdjustment`, `mlPrediction`, etc.

---

### `POST /api/rainfall`
District rainfall dashboard data.

**Request body:**
```json
{ "districtName": "Zomba" }
```

**Response:** `forecast`, `historicalYears`, `historicalValues`, `monthlyDistribution`, `cropSuitability`, `fertilizerCalendar`, `risks`, etc.

---

### `POST /api/chat`
Agricultural chatbot — requires `LOVABLE_API_KEY` in `.env`.

**Request body:**
```json
{
  "messages": [
    { "role": "user", "content": "How much fertilizer should I use for maize?" }
  ]
}
```

**Response:** Standard OpenAI-compatible chat completion object.

---

## Connecting Your Frontend

Replace the Supabase Edge Function calls with calls to this Flask backend.

**Before (Supabase):**
```typescript
const { data } = await supabase.functions.invoke("recommend", { body: payload });
```

**After (Flask):**
```typescript
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL; // e.g. http://localhost:5000

const res  = await fetch(`${BACKEND_URL}/api/recommend`, {
  method:  "POST",
  headers: { "Content-Type": "application/json" },
  body:    JSON.stringify(payload),
});
const data = await res.json();
```

Add `VITE_BACKEND_URL=http://localhost:5000` to your frontend `.env`.

The response shape from each endpoint is **identical** to what the Supabase Edge Functions returned, so no other frontend changes are needed.

---

## Deployment

Any Python-friendly host works: Railway, Render, Fly.io, Heroku, or a plain VPS.

**Render example:**
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn "app:create_app()" --bind 0.0.0.0:$PORT`
- Set `LOVABLE_API_KEY` and `CORS_ORIGINS` as environment variables in the dashboard.
