import ctypes, ctypes.wintypes as wt, time
u=ctypes.windll.user32
class P(wt.POINT): pass
p=P()
pts=[]
for i in range(40):
    u.GetCursorPos(ctypes.byref(p)); pts.append((p.x,p.y)); time.sleep(0.05)
uniq=set(pts)
print("samples",len(pts),"distinct",len(uniq))
print("first",pts[0],"last",pts[-1])
print("maxjump",max((abs(b[0]-a[0])+abs(b[1]-a[1]) for a,b in zip(pts,pts[1:])), default=0))
print("sample trail:", pts[::6])
