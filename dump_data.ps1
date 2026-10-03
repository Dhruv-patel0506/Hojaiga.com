import json

organs = [
    {"id": "11", "name": "Interface", "icon": "??", "color": "#e91e63", "desc": "UI / CLI / Tray", "tasks": ["Ingest user prompt", "Check settings", "Prepare IPC payload"]},
    {"id": "13", "name": "Interface Layer", "icon": "??", "color": "#3f51b5", "desc": "REST/CLI/WS Gateway", "tasks": ["Verify session", "Validate schema", "Forward to dispatch"]},
    {"id": "01", "name": "Brain", "icon": "??", "color": "#9c27b0", "desc": "LLM Task Planning", "tasks": ["Analyze context", "Decompose goals", "Generate plan"]},
    {"id": "14", "name": "LLM Runtime", "icon": "??", "color": "#ff5722", "desc": "Inference Engine", "tasks": ["Load model", "Manage VRAM", "Stream tokens"]},
    {"id": "04", "name": "Knowledge", "icon": "??", "color": "#00bcd4", "desc": "Retrieval & Context", "tasks": ["Read files", "Search DB", "Assemble context"]},
    
    {"id": "02", "name": "CNS Core", "icon": "??", "color": "#00b0ff", "desc": "Master Event/Socket Bus", "tasks": ["Map route", "Parse Event", "Publish"]},
    
    {"id": "05", "name": "Controllers", "icon": "???", "color": "#e91e63", "desc": "Domain Dispatcher", "tasks": ["Match goal", "Map handlers", "Dispatch worker"]},
    {"id": "06", "name": "Automation", "icon": "??", "color": "#9c27b0", "desc": "Browser/GUI Automator", "tasks": ["Load plan", "Coordinate UI", "Route actions"]},
    {"id": "10", "name": "Agents", "icon": "???", "color": "#ff9800", "desc": "Task Sub-Agents", "tasks": ["Resolve role", "Spawn worker", "Verify milestones"]},
    {"id": "15", "name": "Connectors", "icon": "??", "color": "#009688", "desc": "Actuator & I/O", "tasks": ["Init CDP", "Run REST", "Write disk"]},
    {"id": "19", "name": "Chrome CDP", "icon": "??", "color": "#03a9f4", "desc": "Headless Browser", "tasks": ["Launch browser", "Attach debug", "Exec script"]},
    {"id": "24", "name": "DAP", "icon": "???", "color": "#e91e63", "desc": "Desktop Automation", "tasks": ["Query tree", "Inject events", "Manage focus"]},
    
    {"id": "03", "name": "Memory", "icon": "??", "color": "#4caf50", "desc": "State & Sessions", "tasks": ["Load session", "Lock DB", "Persist snapshot"]},
    {"id": "08", "name": "Learning", "icon": "??", "color": "#009688", "desc": "Trace Mining", "tasks": ["Mine trace", "Calc reliability", "Publish metric"]},
    {"id": "22", "name": "Decision", "icon": "??", "color": "#9c27b0", "desc": "Path Selection", "tasks": ["Find alternatives", "Score confidence", "Select path"]},
    {"id": "34", "name": "Task", "icon": "??", "color": "#ff9800", "desc": "Task Scheduler", "tasks": ["Queue task", "Prioritize", "Dispatch"]},
    {"id": "36", "name": "Workflow", "icon": "??", "color": "#e91e63", "desc": "Workflow Compiler", "tasks": ["Parse DAG", "Compile steps", "Exec sequence"]},
    {"id": "26", "name": "Event", "icon": "??", "color": "#ffb300", "desc": "Event Catalog", "tasks": ["Catalog event", "Route payload", "Verify delivery"]},
    
    {"id": "32", "name": "State", "icon": "??", "color": "#9c27b0", "desc": "State Catalog", "tasks": ["Snapshot", "Validate schema", "Persist"]},
    {"id": "07", "name": "Security", "icon": "???", "color": "#ffc107", "desc": "Policy Guard", "tasks": ["Validate policy", "Run auth", "Audit entry"]},
    {"id": "16", "name": "Audit System", "icon": "??", "color": "#795548", "desc": "Immutable Log", "tasks": ["Hash chain", "Write block", "Record metrics"]},
    
    {"id": "09", "name": "Infrastructure", "icon": "??", "color": "#9c27b0", "desc": "Infra Backbone", "tasks": ["Monitor host", "Allocate quota", "Manage base"]},
    {"id": "12", "name": "Integration", "icon": "??", "color": "#8bc34a", "desc": "API Webhooks", "tasks": ["Verify OAuth", "Register hook", "Dispatch"]},
    {"id": "17", "name": "Backup", "icon": "??", "color": "#607d8b", "desc": "Snapshot & Archive", "tasks": ["Prep snapshot", "Compress/Encrypt", "Save catalog"]},
    {"id": "18", "name": "Capability", "icon": "??", "color": "#8d6e63", "desc": "Registry & Discovery", "tasks": ["Index caps", "Rank endpoints", "Resolve"]},
    {"id": "20", "name": "Config Mgr", "icon": "??", "color": "#795548", "desc": "System Configurator", "tasks": ["Load settings", "Validate", "Apply config"]},
    {"id": "21", "name": "Schema", "icon": "??", "color": "#ff5722", "desc": "Validation Rules", "tasks": ["Check schema", "Map types", "Enforce"]},
    {"id": "23", "name": "Dep Mgr", "icon": "??", "color": "#cddc39", "desc": "Graph Resolution", "tasks": ["Analyze graph", "Check loops", "Resolve bounds"]},
    {"id": "25", "name": "Errors", "icon": "??", "color": "#f44336", "desc": "Error Catalog", "tasks": ["Parse stack", "Lookup code", "Remedy"]},
    {"id": "27", "name": "Resource", "icon": "??", "color": "#4caf50", "desc": "Resource Manager", "tasks": ["Monitor", "Allocate RAM", "Free"]},
    {"id": "28", "name": "Service", "icon": "??", "color": "#3f51b5", "desc": "Service Registry", "tasks": ["Register", "Resolve endpoint", "Check health"]},
    {"id": "33", "name": "Manifest", "icon": "??", "color": "#607d8b", "desc": "System Manifest", "tasks": ["Load manifest", "Verify sig", "Apply policy"]},
    {"id": "35", "name": "Update", "icon": "??", "color": "#00bcd4", "desc": "Update Manager", "tasks": ["Check version", "Download patch", "Apply update"]},
    {"id": "kernel", "name": "Kernel", "icon": "??", "color": "#ff9800", "desc": "Boot Manager", "tasks": ["Bootstrap OS", "Mount systems", "Init scheduler"]},
    {"id": "pkg", "name": "Pkg Manager", "icon": "??", "color": "#00bcd4", "desc": "Dependency Installer", "tasks": ["Fetch meta", "Verify sig", "Install bin"]}
]

# We will write a python script to generate HTML. 
with open('d:/new_automation/gen_html.py', 'w', encoding='utf-8') as f:
    f.write('import json\n')
    f.write('organs = ' + json.dumps(organs) + '\n')
    f.write('''
# Output HTML logic here...
def generate():
    pass
''')
