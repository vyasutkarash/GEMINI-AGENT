import streamlit as st
import os
import subprocess
from google import genai
from google.genai import types

# --- 1. SETUP THE APP & API KEY ---
st.set_page_config(page_title="Gemini Coding Agent", page_icon="🤖")
st.title("🤖 Gemini Multi-Agent Developer")
st.caption("I can write, read, and run Python code. Tell me what to build or fix!")

# Grab the API key securely from Streamlit's secrets
if "GEMINI_API_KEY" not in st.secrets:
    st.error("Please add your GEMINI_API_KEY to the Streamlit Secrets!")
    st.stop()

client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# Create a safe folder for the AI to work inside
WORKING_DIR = os.path.abspath("workspace")
os.makedirs(WORKING_DIR, exist_ok=True)

# --- 2. THE PHYSICAL TOOLS ---
def get_files_info(directory="."):
    abs_dir = os.path.abspath(os.path.join(WORKING_DIR, directory))
    if not abs_dir.startswith(WORKING_DIR): return "Error: Outside workspace."
    if not os.path.exists(abs_dir): return "Error: Directory does not exist."
    try:
        contents = os.listdir(abs_dir)
        if not contents: return "Directory is empty."
        res = f"Contents of {directory}:\n"
        for item in contents:
            is_dir = os.path.isdir(os.path.join(abs_dir, item))
            res += f"- {item} [{'DIR' if is_dir else 'FILE'}]\n"
        return res
    except Exception as e: return str(e)

def get_file_content(file_path):
    abs_path = os.path.abspath(os.path.join(WORKING_DIR, file_path))
    if not abs_path.startswith(WORKING_DIR): return "Error: Outside workspace."
    if not os.path.exists(abs_path): return "Error: File does not exist."
    try:
        with open(abs_path, 'r', encoding='utf-8') as f: return f.read(10000)
    except Exception as e: return str(e)

def write_file(file_path, content):
    abs_path = os.path.abspath(os.path.join(WORKING_DIR, file_path))
    if not abs_path.startswith(WORKING_DIR): return "Error: Outside workspace."
    try:
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, 'w', encoding='utf-8') as f: f.write(content)
        return f"Success! Wrote {len(content)} characters to {file_path}."
    except Exception as e: return str(e)

def run_python_file(file_path, args=None):
    abs_path = os.path.abspath(os.path.join(WORKING_DIR, file_path))
    if not abs_path.startswith(WORKING_DIR): return "Error: Outside workspace."
    cmd = ["python3", abs_path]
    if args: cmd.extend(args)
    try:
        res = subprocess.run(cmd, cwd=WORKING_DIR, capture_output=True, text=True, timeout=15)
        out = f"STDOUT:\n{res.stdout}\n"
        if res.stderr: out += f"STDERR:\n{res.stderr}\n"
        return out
    except Exception as e: return str(e)

# --- 3. SCHEMAS & ROUTER ---
agent_tools = [types.Tool(function_declarations=[
    types.FunctionDeclaration(name="get_files_info", description="List files in directory.", parameters=types.Schema(type=types.Type.OBJECT, properties={"directory": types.Schema(type=types.Type.STRING)})),
    types.FunctionDeclaration(name="get_file_content", description="Read a file.", parameters=types.Schema(type=types.Type.OBJECT, properties={"file_path": types.Schema(type=types.Type.STRING)}, required=["file_path"])),
    types.FunctionDeclaration(name="write_file", description="Write a file.", parameters=types.Schema(type=types.Type.OBJECT, properties={"file_path": types.Schema(type=types.Type.STRING), "content": types.Schema(type=types.Type.STRING)}, required=["file_path", "content"])),
    types.FunctionDeclaration(name="run_python_file", description="Run a python script.", parameters=types.Schema(type=types.Type.OBJECT, properties={"file_path": types.Schema(type=types.Type.STRING), "args": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING))}, required=["file_path"]))
])]

agent_config = types.GenerateContentConfig(
    system_instruction="You are an AI coding agent. Explore files, read code, write code, and always run scripts to test your work. You are working in a safe workspace directory.",
    tools=agent_tools,
    temperature=0.0
)

def execute_tool(func_call):
    name, args = func_call.name, func_call.args
    if name == "get_files_info": return get_files_info(args.get("directory", "."))
    elif name == "get_file_content": return get_file_content(args["file_path"])
    elif name == "write_file": return write_file(args["file_path"], args["content"])
    elif name == "run_python_file": return run_python_file(args["file_path"], args.get("args", []))
    return "Error: Tool not found."

# --- 4. STREAMLIT CHAT UI & LOOP ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Show past messages
for msg in st.session_state.messages:
    role = "user" if msg.role == "user" else "assistant"
    # Only print text parts to the screen, hide the ugly tool JSON
    if msg.parts and msg.parts[0].text:
        with st.chat_message(role):
            st.write(msg.parts[0].text)

# Chat Input Box
user_prompt = st.chat_input("E.g., Write a python script that calculates the Fibonacci sequence, save it, and run it.")

if user_prompt:
    # 1. Show user message
    with st.chat_message("user"): st.write(user_prompt)
    
    # 2. Add to AI's memory
    st.session_state.messages.append(types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)]))
    
    with st.chat_message("assistant"):
        status_box = st.status("Agent is thinking...", expanded=True)
        
        # 3. The Agentic Loop
        for i in range(10): # Max 10 turns
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=st.session_state.messages,
                config=agent_config
            )
            
            # Save AI's response to memory
            if response.candidates and response.candidates[0].content:
                st.session_state.messages.append(response.candidates[0].content)
            
            # Did it call a tool?
            if response.function_calls:
                func_call = response.function_calls[0]
                status_box.write(f"🔧 Running tool: `{func_call.name}`")
                
                # Run the tool
                tool_res = execute_tool(func_call)
                
                # Give result back to memory
                st.session_state.messages.append(types.Content(role="user", parts=[types.Part.from_function_response(name=func_call.name, response={"result": str(tool_res)})]))
            else:
                # Finished!
                status_box.update(label="Task Complete!", state="complete", expanded=False)
                st.write(response.text)
                break
