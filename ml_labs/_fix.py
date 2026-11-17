p = 'ml_with_python_full_course_lab.html'
s = open(p, encoding='utf-8').read()
old = "raise the learning rate.'}`);\n  }\n  run();"
new = "raise the learning rate.'}`);\n  }\n  gdRun();"
print('found:', old in s)
s2 = s.replace(old, new, 1)
print('changed:', s2 != s)
open(p, 'w', encoding='utf-8').write(s2)
