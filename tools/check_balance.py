import re
import sys
p = sys.argv[1]
s = open(p, encoding='utf-8').read()
pairs = {'(':')','[':']','{':'}','`':'`','"':'"',"'":"'"}
stack=[]
for i,ch in enumerate(s):
    if ch in '([{' : stack.append((ch,i))
    elif ch in ')]}':
        if not stack:
            print('Unmatched closing', ch, 'at', i); break
        o,oi = stack.pop()
        if pairs[o] != ch:
            print('Mismatched', o, 'at', oi, 'with', ch, 'at', i); break
print('stack remaining:', stack[:3])
print('done')
