// Pointer lab target (WPF). Same log format as lab_winforms.cs. WPF reads the Windows pointer stack (WM_POINTER*) when present, mouse messages otherwise.
using System; using System.IO; using System.Windows; using System.Windows.Controls; using System.Windows.Input; using System.Windows.Media; using System.Windows.Interop;
class Lab : Window {
  StreamWriter log; Grid grid; Canvas canvas; Border target; TextBlock src;
  void L(string kind, Point p, int delta, string extra){
    var c = System.Windows.Forms.Cursor.Position;
    string s = "{\"t\":"+Environment.TickCount+",\"kind\":\""+kind+"\",\"x\":"+(int)p.X+",\"y\":"+(int)p.Y+",\"delta\":"+delta+",\"poll_x\":"+c.X+",\"poll_y\":"+c.Y
      +",\"poll_btn\":\""+System.Windows.Forms.Control.MouseButtons+"\",\"mods\":\""+Keyboard.Modifiers+"\""+(extra!=null?","+extra:"")+"}";
    lock(log){ log.WriteLine(s); log.Flush(); }
  }
  int a_x = -30000, a_y = -30000;
  Lab(string path, int ax, int ay){ a_x = ax; a_y = ay; Init(path); }
  void Init(string path){
    log = new StreamWriter(new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.ReadWrite));
    Title = "HojaigaPointerLab-WPF"; Width = 900; Height = 600; Left = a_x; Top = a_y; WindowStartupLocation = WindowStartupLocation.Manual;
    grid = new Grid(); grid.ColumnDefinitions.Add(new ColumnDefinition{ Width = new GridLength(600) }); grid.ColumnDefinitions.Add(new ColumnDefinition());
    canvas = new Canvas{ Background = Brushes.White }; target = new Border{ Background = Brushes.LightYellow, AllowDrop = true }; Grid.SetColumn(target, 1);
    src = new TextBlock{ Text = "DRAG ME", Background = Brushes.LightBlue, Width = 120, Height = 40 }; Canvas.SetLeft(src, 20); Canvas.SetTop(src, 20); canvas.Children.Add(src);
    grid.Children.Add(canvas); grid.Children.Add(target); Content = grid;
    foreach (var pair in new[]{ Tuple.Create((UIElement)canvas,"canvas"), Tuple.Create((UIElement)target,"target"), Tuple.Create((UIElement)src,"src") }){
      var el = pair.Item1; var nm = pair.Item2;
      el.MouseDown += (s,e)=>{ L("down:"+nm+":"+e.ChangedButton, e.GetPosition(el), 0, null); };
      el.MouseUp += (s,e)=>{ L("up:"+nm+":"+e.ChangedButton, e.GetPosition(el), 0, null); };
      el.MouseMove += (s,e)=>{ L("move:"+nm, e.GetPosition(el), 0, null); };
      el.MouseWheel += (s,e)=>{ L("wheel:"+nm, e.GetPosition(el), e.Delta, null); };
    }
    src.MouseMove += (s,e)=>{ if (e.LeftButton == MouseButtonState.Pressed){ DragDrop.DoDragDrop(src, "lab-payload", DragDropEffects.Copy); L("dragdrop_returned", new Point(), 0, null);} };
    target.DragEnter += (s,e)=>{ e.Effects = DragDropEffects.Copy; L("dragenter", new Point(), 0, null); };
    target.Drop += (s,e)=>{ L("drop", new Point(), 0, "\"data\":\""+e.Data.GetData(DataFormats.Text)+"\""); };
    PreviewKeyDown += (s,e)=>{ L("keydown:"+e.Key, new Point(), 0, "\"kc\":\""+e.Key+"\",\"ctrl\":"+((Keyboard.Modifiers & ModifierKeys.Control)!=0?1:0)+",\"shift\":"+((Keyboard.Modifiers & ModifierKeys.Shift)!=0?1:0)); };
    Loaded += (s,e)=>{ lock(log){ log.WriteLine("{\"kind\":\"ready\",\"hwnd\":"+new WindowInteropHelper(this).Handle.ToInt64()+"}"); log.Flush(); } };
  }
  [STAThread] static void Main(string[] a){ new Application().Run(new Lab(a.Length>0?a[0]:"lab_wpf.log", a.Length>2?int.Parse(a[1]):-30000, a.Length>2?int.Parse(a[2]):-30000)); }
}
