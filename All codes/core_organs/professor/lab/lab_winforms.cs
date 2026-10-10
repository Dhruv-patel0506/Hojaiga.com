// Pointer lab target (WinForms / classic Win32 message toolkit). Logs every mouse event it receives as JSON lines:
//   event kind, position the MESSAGE carried, position the app would read by POLLING (Cursor.Position), buttons by polling, modifiers.
// Left half = canvas, right half = drop target. A label on the left can be dragged (OLE drag and drop) onto the right half.
using System; using System.Drawing; using System.IO; using System.Windows.Forms; using System.Text;
class Lab : Form {
  StreamWriter log; Panel canvas, target; Label src; Point last; bool down; Point downAt;
  static string Esc(string s){ return s.Replace("\\","\\\\").Replace("\"","\\\""); }
  void L(string kind, MouseEventArgs e, string extra){
    Point c = Cursor.Position;
    string s = "{\"t\":"+Environment.TickCount+",\"kind\":\""+kind+"\",\"x\":"+(e!=null?e.X:0)+",\"y\":"+(e!=null?e.Y:0)+",\"btn\":\""+(e!=null?e.Button.ToString():"")+"\",\"delta\":"+(e!=null?e.Delta:0)
      +",\"poll_x\":"+c.X+",\"poll_y\":"+c.Y+",\"poll_btn\":\""+Control.MouseButtons+"\",\"mods\":\""+Control.ModifierKeys+"\""+(extra!=null?","+extra:"")+"}";
    lock(log){ log.WriteLine(s); log.Flush(); }
  }
  int a_x = -30000, a_y = -30000;
  Lab(string path, int ax, int ay){ a_x = ax; a_y = ay; Init(path); }
  void Init(string path){
    log = new StreamWriter(new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.ReadWrite));
    Text = "HojaigaPointerLab-WinForms"; Width = 900; Height = 600; StartPosition = FormStartPosition.Manual; Location = new Point(a_x, a_y);
    canvas = new Panel{ Dock = DockStyle.Left, Width = 600, BackColor = Color.White };
    target = new Panel{ Dock = DockStyle.Fill, BackColor = Color.LightYellow, AllowDrop = true };
    src = new Label{ Text = "DRAG ME", Left = 20, Top = 20, Width = 120, Height = 40, BackColor = Color.LightBlue };
    canvas.Controls.Add(src); Controls.Add(target); Controls.Add(canvas);
    foreach (Control c in new Control[]{canvas, target, src}){
      Control cc = c; string nm = c==canvas?"canvas":(c==target?"target":"src");
      c.MouseDown += (s,e)=>{ down = true; downAt = e.Location; L("down:"+nm, e, null); };
      c.MouseUp += (s,e)=>{ down = false; L("up:"+nm, e, null); };
      c.MouseMove += (s,e)=>{ last = e.Location; L("move:"+nm, e, null); if (nm=="canvas") canvas.Invalidate(); };
      c.MouseWheel += (s,e)=>{ L("wheel:"+nm, e, null); };
      c.DoubleClick += (s,e)=>{ L("dblclick:"+nm, null, null); };
      c.MouseClick += (s,e)=>{ L("click:"+nm, e, null); };
    }
    src.MouseMove += (s,e)=>{ if (e.Button == MouseButtons.Left && (Math.Abs(e.X-downAt.X)>6 || Math.Abs(e.Y-downAt.Y)>6)){ down=false; src.DoDragDrop("lab-payload", DragDropEffects.Copy); L("dragdrop_returned", null, null);} };
    target.DragEnter += (s,e)=>{ e.Effect = DragDropEffects.Copy; L("dragenter", null, null); };
    target.DragDrop += (s,e)=>{ L("drop", null, "\"data\":\""+Esc(e.Data.GetData(DataFormats.Text)+"")+"\""); };
    canvas.Paint += (s,e)=>{ e.Graphics.DrawLine(Pens.Red, last.X-10, last.Y, last.X+10, last.Y); e.Graphics.DrawLine(Pens.Red, last.X, last.Y-10, last.X, last.Y+10); };
    KeyPreview = true;
    KeyDown += (s,e)=>{ L("keydown:"+e.KeyCode, null, "\"kc\":\""+e.KeyCode+"\",\"ctrl\":"+(e.Control?1:0)+",\"shift\":"+(e.Shift?1:0)+",\"alt\":"+(e.Alt?1:0)); };
    Shown += (s,e)=>{ lock(log){ log.WriteLine("{\"kind\":\"ready\",\"hwnd\":"+Handle.ToInt64()+"}"); log.Flush(); } };
  }
  [STAThread] static void Main(string[] a){ Application.EnableVisualStyles(); Application.Run(new Lab(a.Length>0?a[0]:"lab_winforms.log", a.Length>2?int.Parse(a[1]):-30000, a.Length>2?int.Parse(a[2]):-30000)); }
}
