"""Start only this edition; the larger app can remain running on port 8502."""

import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.api:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8503"))
    )
