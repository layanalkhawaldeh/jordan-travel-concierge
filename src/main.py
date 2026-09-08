import sys
import os
# Add the 'src' directory to python path to resolve internal imports (like 'from schemas import...')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from src.services.conversation_service import create_conversation

from src.database import get_db, init_db, ConversationModel, SalesLeadModel, AgentExecutionLogModel
from src.seed_data import seed_database
from src.agent_core import run_tourism_agent
import src.config as config

app = FastAPI(
    title="Jordan Tourism Trip Planning & Sales Agent API",
    description="LLM & Agentic AI Tourism Assistant with Tool Calling & PostgreSQL persistence.",
    version="2.0.0"
)

app.mount("/static", StaticFiles(directory="/app/static"), name="static")

# Startup event to automatically seed the database
@app.on_event("startup")
def startup_db():
    print("Initializing Database and seeding data on startup...")
    try:
        seed_database()
        from src.services.rag_service import seed_knowledge_base
        seed_knowledge_base()
    except Exception as e:
        print(f"Database seeding failed: {e}")

class ChatRequest(BaseModel):
    conversation_id: str = Field(description="Unique ID for tracking conversation state.")
    message: str = Field(description="The user input message.")
    model_name: Optional[str] = Field(default=None, description="Optional Gemini model override.")

class ChatResponse(BaseModel):
    response: str = Field(description="The agent's text response in English.")
    steps: List[Dict[str, Any]] = Field(description="List of tools executed during the agent loop.")
    metadata: Dict[str, Any] = Field(description="Execution metrics including tokens, latency, cost, and iterations.")

@app.post("/conversations")
def create_conversation_endpoint(
    db: Session = Depends(get_db)#فكرة ال depends انو الفنكشن عنا عشان ينشئ شات بالداتا بيس بحاجة اداة اتصال ف الديبينز بتولى هاي العملية
):
    conversation = create_conversation(db=db)

    return {
        "conversation_id": conversation.id,
        "title": conversation.title,
        "status": conversation.status,#(conversation lifecycle : active/completed)
        "created_at": conversation.created_at.isoformat()
        if conversation.created_at else None,
        "updated_at": conversation.updated_at.isoformat()
        if conversation.updated_at else None,
        "message_count": 0,
        "preview": "New conversation"
    }

@app.post("/chat", response_model=ChatResponse)#السيرفر النهائي لازم يكن مطابق للسكيما تبعت ال شات ريسبونس
async def chat(request: ChatRequest):
    """
    Core agent endpoint that processes user messages, executes tools,
    and maintains conversation state.
    """
    if not request.conversation_id or not request.message.strip():
        raise HTTPException(status_code=400, detail="conversation_id and message are required.")
    
    try:
        response_text, steps, metadata = run_tourism_agent(
            conversation_id=request.conversation_id,
            user_message=request.message,
            model_name=request.model_name
        )
        return ChatResponse(response=response_text, steps=steps, metadata=metadata)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent loop error: {str(e)}")

@app.get("/conversations")
async def list_conversations(db: Session = Depends(get_db)):
    """
    List all active conversation sessions stored in the database.
    """
    convs = db.query(ConversationModel).order_by(ConversationModel.updated_at.desc()).all()#بنرتبهم تنازليا عشان يترتبو حسب اخر تعديل
    return [
        {
            "conversation_id": c.id,
            "title": c.title or "New conversation",
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "preview": c.messages[-1]["content"][:40] + "..." if c.messages else "New conversation"#بنشوف اخر مسج انبعتت وبناخد اول 40 حرف وبنحطها بالسايدبار عشان تكون زي معاينة سريعة للشات
        } for c in convs
    ]

@app.get("/conversations/{conversation_id}")#(لما اكبس على شات)
async def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    """
    Fetch history and structured traveler profile for a specific conversation.
    """
    conv = db.query(ConversationModel).filter(ConversationModel.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {
        "conversation_id": conv.id,
        "traveler_profile": conv.traveler_profile,
        "messages": conv.messages
    }

class RenameRequest(BaseModel):
    title: str = Field(..., max_length=100, description="The new custom title for the conversation.")

@app.post("/conversations/{conversation_id}/rename")
async def rename_conversation(conversation_id: str, request: RenameRequest, db: Session = Depends(get_db)):
    """
    Rename a conversation's title.
    """
    conv = db.query(ConversationModel).filter(ConversationModel.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    conv.title = request.title
    db.commit()
    return {"status": "success", "message": "Conversation renamed successfully.", "title": conv.title}

@app.delete("/conversations/{conversation_id}")
async def delete_conversation_endpoint(conversation_id: str, db: Session = Depends(get_db)):
    """
    Delete a conversation and its execution logs.
    """
    from src.services.conversation_service import delete_conversation
    success = delete_conversation(db, conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    
    # Clean up logs
    db.query(AgentExecutionLogModel).filter(AgentExecutionLogModel.conversation_id == conversation_id).delete()
    db.commit()
    return {"status": "success", "message": "Conversation deleted successfully."}

@app.get("/conversations/{conversation_id}/logs")
async def get_conversation_logs(conversation_id: str, db: Session = Depends(get_db)):
    """
    Fetch execution logs for a specific conversation.
    """
    logs = db.query(AgentExecutionLogModel)\
             .filter(AgentExecutionLogModel.conversation_id == conversation_id)\
             .order_by(AgentExecutionLogModel.created_at.desc())\
             .all()
    return logs

@app.get("/admin/logs")
async def get_logs(db: Session = Depends(get_db)):
    """
    Fetch all agent execution logs for observability.
    """
    logs = db.query(AgentExecutionLogModel).order_by(AgentExecutionLogModel.created_at.desc()).limit(50).all()
    return logs

@app.get("/admin/leads")#هاد بستخدمه لما الايجنت ينهي الشات ويحدد الشغلات بيجي موظف المبيعات بفتح الداشبورد تبعه والسيستم بنادي لمسار 
#مع تأكيد طلبه وبحكيله احكي مع الزبون لتتفقو عالتثبيت والدفع 
async def get_leads(db: Session = Depends(get_db)):
    """
    Fetch all submitted qualified sales leads.
    """
    leads = db.query(SalesLeadModel).order_by(SalesLeadModel.created_at.desc()).all()
    return leads

class ReviewRequest(BaseModel):
    status: str = Field(description="approved, rejected, or modified")
    comments: Optional[str] = Field(default=None, description="Comments from the reviewer")
    reviewer_name: str = Field(description="Name of the reviewer")

@app.get("/admin/bookings")
async def get_bookings(db: Session = Depends(get_db)):
    """
    Fetch all direct sandbox bookings.
    """
    from src.database import BookingModel
    bookings = db.query(BookingModel).order_by(BookingModel.created_at.desc()).all()
    return bookings

@app.post("/admin/leads/{lead_id}/review")
async def review_lead(lead_id: str, request: ReviewRequest, db: Session = Depends(get_db)):
    """
    Review a qualified sales lead (approve, reject, or modify).
    """
    from datetime import datetime, timezone
    lead = db.query(SalesLeadModel).filter(SalesLeadModel.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Sales lead not found.")
    
    lead.status = request.status
    lead.reviewer_comments = request.comments
    lead.reviewer_name = request.reviewer_name
    lead.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "success", "message": f"Lead {lead_id} status updated to {request.status}."}

@app.post("/admin/bookings/{booking_id}/review")
async def review_booking(booking_id: str, request: ReviewRequest, db: Session = Depends(get_db)):
    """
    Review a direct sandbox booking.
    """
    from datetime import datetime, timezone
    from src.database import BookingModel
    booking = db.query(BookingModel).filter(BookingModel.booking_id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    
    booking.status = request.status
    profile = dict(booking.traveler_profile or {})
    profile["reviewer_comments"] = request.comments
    profile["reviewed_by"] = request.reviewer_name
    profile["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    booking.traveler_profile = profile
    db.commit()
    return {"status": "success", "message": f"Booking {booking_id} status updated to {request.status}."}

class BookingCreateRequest(BaseModel):
    conversation_id: str

@app.post("/bookings")
async def create_booking_endpoint(request: BookingCreateRequest):
    """Exposes direct endpoint to initiate a booking reservation."""
    import json
    from src.tools.operations import create_booking
    res = create_booking(request.conversation_id)
    res_json = json.loads(res)
    if not res_json.get("success"):
        raise HTTPException(status_code=400, detail=res_json.get("error"))
    return res_json

@app.post("/bookings/{booking_id}/pay")
async def pay_booking_endpoint(booking_id: str):
    """Exposes direct endpoint to simulate payment and confirm booking."""
    import json
    from src.tools.operations import confirm_booking_payment
    res = confirm_booking_payment(booking_id)
    res_json = json.loads(res)
    if not res_json.get("success"):
        raise HTTPException(status_code=400, detail=res_json.get("error"))
    return res_json


@app.post("/admin/initdb")
async def init_and_seed():
    """
    Helper endpoint to manually trigger database initialization and seeding.
    """
    try:
        seed_database()
        return {"status": "success", "message": "Database initialized and seeded successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database initialization failed: {str(e)}")

@app.get("/health")#عشان يتأكد انو شغال ومش معلق لو رجع 200 الوضع تمام
async def health_check():
    return {
        "status": "healthy",
        "gemini_api_configured": config.GEMINI_API_KEY is not None,
        "default_model": config.DEFAULT_MODEL
    }

# Premium HTML Chat Dashboard UI (Loaded from separate template)
@app.get("/", response_class=HTMLResponse)#قيت للرابط الاساسي للموقع واتاكد انو صفحة ويب مش جيسن 
async def main_chat_ui():
    """Loads index.html dynamically to serve the user-facing split screen interface."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(current_dir, "templates", "index.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="HTML template file templates/index.html not found.")
    
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read index.html: {e}")
