import json,glob,sys
def show(o,ind=0):
    p=' '*ind
    if isinstance(o,dict):
        for k,v in o.items():
            if isinstance(v,(dict,list)):
                print(p+str(k)+':'); show(v,ind+2)
            else: print(p+str(k)+': '+str(v))
    elif isinstance(o,list):
        for x in o:
            if isinstance(x,(dict,list)):
                print(p+'-'); show(x,ind+2)
            else: print(p+'- '+str(x))
for f in sys.argv[1:]:
    d=json.load(open(f,encoding='utf-8'))
    print('#####',f); show(d)
