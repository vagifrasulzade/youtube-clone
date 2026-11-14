from fastapi import FastAPI

app = FastAPI(title="YouTube Clone API")

@app.get("/")
def home():
    return {"message": "YouTube Clone API is running!"}