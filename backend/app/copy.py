
# Anthropic wallet is out of credit.
BUDGET_EXHAUSTED = "API budget for today is used up 🪫... check back soon."
# Anthropic's own 429 (upstream busy) — distinct from our per-IP throttle.
UPSTREAM_BUSY = "A bit busy right now... give it a moment and try again."
# Misconfiguration (missing/invalid key, permissions).
CONFIG_ISSUE = "Service configuration issue on our end... we've been notified."
# Per-IP burst throttle (slowapi, per minute).
RATE_LIMIT_MINUTE = "Slow down, champ 😄... give it a few seconds and try again."
# Per-IP daily ceiling (slowapi, per day).
RATE_LIMIT_DAY = "You've had your share of the demo for today 🫗... come back tomorrow!"
# Global shared daily budget spent.
DAILY_CAP = "That's a wrap for today 🎬... the daily budget is spent. Come back tomorrow!"
# Anything unexpected in the pipeline.
GENERIC = "Something went sideways generating your query... try rephrasing?"
# No model key configured at all.
NO_KEY = "The demo isn't configured with a model key right now... check back soon."
