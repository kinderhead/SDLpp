from pycparser import c_ast, parse_file, preprocess_file
from typing import Any, Literal, NamedTuple
import json


flags: dict[str, str | Literal[False]] = {}
objects: dict[str, Any] = {}
built_funcs: list[str] = []
# pointerless = ["SDL_Rect"]

class Arg(NamedTuple):
    type: str
    name: str
    
    def __eq__(self, other):
        return self.type == other.type and self.name == other.name

class FuncDef(NamedTuple):
    ret: str
    name: str
    args: list[Arg]
    
    file: str
    line: int
    
    err: bool
    get_list: bool
    get_obj: Arg | None
    get_point: bool
    get_rect: bool
    get_fpoint: bool
    get_frect: bool
    
    def get_ret_type(self):
        if self.get_obj is not None:
            return self.get_obj.type[:-1]
        return self.ret

class FuncDefVisitor(c_ast.NodeVisitor):
    funcs: list[FuncDef] = []
    
    def visit_Decl(self, node: c_ast.Decl):
        if not str(node.name).startswith("SDL_") or "linux" in str(node.name).lower() or "builtin" in str(node.name).lower() or node.coord.file.endswith("SDL_stdinc.h"): # type: ignore
            return
        if type(node.type) == c_ast.FuncDecl and type(node.type.args) == c_ast.ParamList:
            args: list[Arg] = []
            ret_type = get_type(node.type.type)
            err = has_err(node.name, node.coord.file, node.coord.line) # type: ignore
            if err and ret_type == "bool":
                ret_type = "void"
            for i in node.type.args.params:
                if type(i) == c_ast.EllipsisParam:
                    return
                    #args.append(Arg("...", ""))
                else:
                    if (i.name is not None):
                        args.append(Arg(get_type(i.type), i.name))
            
            get_list = False
            get_obj = None
            get_point = False
            get_rect = False
            get_fpoint = False
            get_frect = False
            if len(args) != 0:
                if args[-1] == Arg("int*", "count"):
                    args.pop()
                    get_list = True
                elif str(node.name).startswith("SDL_Get") and ret_type == "void":
                    last_is_ptr = True
                    for idex, i in enumerate(args):
                        if i.type[:-1] in objects.keys() or idex == len(args) - 1:
                            continue
                        if "*" in i.type:
                            last_is_ptr = False
                            break
                    if "*" in args[-1].type and last_is_ptr:
                        get_obj = args.pop()
                    elif len(args) == 2 and args[0].type == "int*" and args[1].type == "int*":
                        get_point = True
                    elif len(args) == 3 and args[0].type[:-1] in objects.keys() and args[1].type == "int*" and args[2].type == "int*":
                        get_point = True
                    elif len(args) == 4 and args[0].type == "int*" and args[1].type == "int*" and args[2].type == "int*" and args[3].type == "int*":
                        get_rect = True
                    elif len(args) == 5 and args[0].type[:-1] in objects.keys() and args[1].type == "int*" and args[2].type == "int*" and args[3].type == "int*" and args[4].type == "int*":
                        get_rect = True
                    elif len(args) == 2 and args[0].type == "float*" and args[1].type == "float*":
                        get_fpoint = True
                    elif len(args) == 3 and args[0].type[:-1] in objects.keys() and args[1].type == "float*" and args[2].type == "float*":
                        get_fpoint = True
                    elif len(args) == 4 and args[0].type == "float*" and args[1].type == "float*" and args[2].type == "float*" and args[3].type == "float*":
                        get_frect = True
                    elif len(args) == 5 and args[0].type[:-1] in objects.keys() and args[1].type == "float*" and args[2].type == "float*" and args[3].type == "float*" and args[4].type == "float*":
                        get_frect = True
                        
            self.funcs.append(FuncDef(ret_type, node.name, args, node.coord.file, node.coord.line, err, get_list, get_obj, get_point, get_rect, get_fpoint, get_frect)) # type: ignore


def get_macros():
    data = preprocess_file("SDL/include/SDL3/SDL.h", cpp_args=["-dM"]).splitlines() # type: ignore
    
    def name(i: str): return i.split(' ')[1]
    def val(i: str): return i.split(f"#define {name(i)} ")[1]
    
    data = [(name(i), val(i)) for i in data if name(i).startswith("SDL_") and "renamed" not in val(i) and not name(i).startswith("SDL_WINDOW_SURFACE_VSYNC") and not name(i).startswith("SDL_INIT_INTERFACE")]
    return dict(data)

def get_type(t: c_ast.TypeDecl):
    if type(t.type) == c_ast.IdentifierType:
        assert not ("Flags" in t.type.names[0] and t.type.names[0] not in flags.keys()), t.type.names[0]
        if t.type.names[0] in flags.keys() and flags[t.type.names[0]] != False:
            return " ".join(t.quals + t.type.names).replace("SDL_", "SDL::")
        return " ".join(t.quals + t.type.names)
    elif type(t) == c_ast.PtrDecl:
        return get_type(t.type) + "*"
    else:
        raise Exception()
    
def has_err(name: str, file: str, line: int):
    if name == "SDL_GetError" or name.endswith("builtin") or name in ["SDL_Swap16", "SDL_Swap32", "SDL_Swap64"]:
        return False
    
    with open(file, "r") as f:
        data = f.readlines()
        assert data[line - 2] == " */\n"
        
        x = line - 3
        while True:
            if "/**" in data[x]:
                return False
            if "SDL_GetError()" in data[x]:
                return True
            x -= 1
    
def get_raw_ns(funcs: list[FuncDef]):
    txt = "namespace raw\n{\n"
    
    for i in funcs:
        txt += f"//! @copydoc {i.name}()\n"
        
        args = list(i.args)
        if i.get_list:
            args.append(Arg("int*", "count"))
        elif i.get_obj is not None:
            args.append(i.get_obj)
        
        txt += f"inline {i.ret} {i.name.split('SDL_')[1]}({', '.join(map(lambda e: e.type + ' ' + e.name, args))}) {{ "
        
        ret = "return "
        if i.ret == "void":
            ret = ""
        elif "::" in i.ret:
            ret = f"return ({i.ret}) "
        
        func_call = f"{i.name}({', '.join(map(lambda e: e.name, args))});"
        
        if not i.err:
            txt += f"{ret}{func_call}"
        elif ret == "":
            txt += f"auto _ret = {func_call} if (!_ret) throw SDL::Error(SDL::raw::GetError());"
        else:
            txt += f"auto _ret = {func_call} if (!_ret) throw SDL::Error(SDL::raw::GetError()); {ret}_ret;"
            
        txt += f" }}\n\n" # f string because it makes vscode happy
    
    return txt + "}"

def get_enums():
    txt = ""
    
    for k, v in flags.items():
        if v == False:
            continue
        
        txt += f"enum {k.split('SDL_')[1]}\n{{\n"
        
        for k2, v2 in macros.items():
            if k2.startswith(v):
                txt += f"    {k2.split(v)[1]} = {v2},\n"
        
        txt = txt[:-2] + f"\n}};\n\n"  # make vscode happy again
    
    return txt

def should_replace_ptr(type: str):
    return "SDL_Rect" in type or "SDL_FRect" in type or "SDL_Point" in type or "SDL_FPoint" in type

def sanitize_type(type: str, returning = False, as_list = False):
    if as_list:
        if type.strip("*") in objects.keys() or "char*" in type:
            return f"std::vector<{sanitize_type(type, returning)}>"
        else:
            return f"std::vector<{sanitize_type(type, returning)[:-1]}>"
    
    if type.strip("*") in objects.keys():
        return f"std::shared_ptr<{type.replace('SDL_', 'SDL::').replace('*', '')}>"
    elif "char*" in type and returning:
        return "std::string"
    elif "char*" in type:
        return "std::string&"
    elif should_replace_ptr(type):
        type = type.replace('SDL_', 'SDL::').replace("*", "&")
        # if "const" in type:
        #     return type.replace("const ", "").replace("*", "")
        # elif "*" in type:
        #     return type.replace("*", "&")
    return type

def sanitize_args(args: list[Arg]):
    return ", ".join([sanitize_type(i.type) + " " + i.name for i in args])

def sanitize_call(args: list[Arg]):
    clean: list[str] = []

    for i in args:
        if i.type.strip("*") in objects.keys():
            clean.append(f"{i.name}->get()")
        elif "char*" in i.type and "**" not in i.type:
            clean.append(f"{i.name}.c_str()")
        elif should_replace_ptr(i.type):
            clean.append(f"&{i.name}")
        else:
            clean.append(f"{i.name}")

    return ", ".join(clean)

def sanitize_return(type: str, expr: str, guarantee_not_ptr = False):
    if type.strip("*") in objects.keys():
        return f"{type.replace('SDL_', 'SDL::').replace('*', '')}::get({expr})"
    if not guarantee_not_ptr and should_replace_ptr(type):
        return f"*{expr}"
    return expr

def gen_func_body(func: FuncDef, this = False):
    ret = "return "
    if func.ret == "void":
        ret = ""
    elif "::" in func.ret:
        ret = f"return ({func.ret}) "
    
    end_type = sanitize_type(func.ret, True)
    called = ""
    
    if this:
        called = f'{get_func(func.name)}({sanitize_call([Arg("this", "_ptr")] + func.args[1:])}'
    else:
        called = f'{get_func(func.name)}({sanitize_call(func.args)}'
    
    if func.get_list:
        if end_type.endswith("*"):
            end_type = end_type[:-1]
        return f"""int _count; std::vector<{end_type}> _items; auto _ret = {called}, &_count); for (int i = 0; i < _count; i++) _items.push_back({sanitize_return(func.ret, '_ret[i]')}); return _items;""".replace("(, ", "(")
    elif func.get_obj is not None:
        return f"""{func.get_obj.type[:-1]} _out; {called}, &_out); return {sanitize_return(func.get_obj.type, "_out", True)};""".replace("(, ", "(")
    else:
        return f"""{ret}{sanitize_return(func.ret, called)});"""

def get_func(func: str):
    return func.replace("SDL_", "SDL::raw::")

def build_func_def(func: FuncDef, name: str | None, this: bool):
    if name is None:
        name = func.name.replace("SDL_", "")
        
    if this:
        caller = f"{get_func(func.name)}(_ptr, "
    else:
        caller = f"{get_func(func.name)}("
    
    if func.get_point:
        ret = "SDL::Point"
        args = ""
        body = f"""SDL::Point _p = {{}}; {caller}&_p.x, &_p.y); return _p;"""
    elif func.get_rect:
        ret = "SDL::Rect"
        args = ""
        body = f"""SDL::Rect _r = {{}}; {caller}&_r.x, &_r.y, &_r.w, &_r.h); return _r;"""
    elif func.get_fpoint:
        ret = "SDL::FPoint"
        args = ""
        body = f"""SDL::FPoint _p = {{}}; {caller}&_p.x, &_p.y); return _p;"""
    elif func.get_frect:
        ret = "SDL::FRect"
        args = ""
        body = f"""SDL::FRect _r = {{}}; {caller}&_r.x, &_r.y, &_r.w, &_r.h); return _r;"""
    else:
        ret = sanitize_type(func.get_ret_type(), True, func.get_list)
        if this:
            args = sanitize_args(func.args[1:])
        else:
            args = sanitize_args(func.args)
        body = gen_func_body(func, this)
    
    if this:
        return f"""inline {ret} {name}({args}) const {{ {body} }}"""
    else:
        return f"""inline {ret} {name}({args}) {{ {body} }}"""

def get_classes(funcs: list[FuncDef]):
    txt = "\n\n"
    
    for cls, info in objects.items():
        def replaced_name(func: str):
            for i in info["remove"]:
                func = func.replace(i, "")
            return func.replace("SDL_", "")
        
        name = cls.split("SDL_")[1]

        txt += f"class {name}\n{{\n"
        
        txt += f"    {cls}* _ptr;\n"
        txt += f"    bool _block_destroy;\n"
        txt += f"    {name}({cls}* ptr, bool block_destroy) : _ptr(ptr), _block_destroy(block_destroy) {{ }}\npublic:\n"
        
        for c in info["init"]:
            constructor = [i for i in funcs if i.name == c][0]
            txt += f"    static inline std::shared_ptr<{name}> Create({sanitize_args(constructor.args)}) {{ return get({get_func(constructor.name)}({sanitize_call(constructor.args)})); }}\n"
        
        txt += f"\n    {name}(const {name}&) = delete;"
        if info["destroy"] != "":
            txt += f"\n    ~{name}() {{ if (!_block_destroy) {get_func(info['destroy'])}(_ptr); }}"
        txt += f"\n    {name}& operator=(const {name}&) = delete;\n\n"
        
        for i in funcs:
            if i.name == info['destroy']:
                continue
            if "patches" in info and i.name in info['patches']:
                txt += f"    {info['patches'][i.name]}\n"
                built_funcs.append(i.name)
            elif len(i.args) != 0 and i.args[0].type == f"{cls}*":
                txt += f"""    {build_func_def(i, replaced_name(i.name), True)}\n"""
                built_funcs.append(i.name)
        
        txt += f"\n    inline {cls}* get() const {{ return _ptr; }}\n"
        txt += f"""\n    static inline std::shared_ptr<{name}> get({cls}* ptr, bool block_destroy = false)
    {{
        auto& entry = _ptrs[ptr];
        if (!entry.expired()) return entry.lock();
        std::shared_ptr<{name}> obj(new {name}(ptr, block_destroy));
        entry = obj;
        return obj;
    }}\n"""
        
        txt += f"""private:
    static std::unordered_map<{cls}*, std::weak_ptr<{name}>> _ptrs;
"""
        
        txt += f"}};\n\n"  # make vscode happy again
    
    return txt[:-1]

def get_extra_funcs(funcs: list[FuncDef]):
    txt = ""
    
    for i in funcs:
        if i.name in built_funcs:
            continue
        
        txt += f"{build_func_def(i, None, False)}\n"
    
    return txt[:-1]

macros = get_macros()

with open("flags.json", "r") as f:
    flags = json.load(f)
    
with open("objects.json", "r") as f:
    objects = json.load(f)

ast = parse_file("SDL/include/SDL3/SDL.h", use_cpp=True, cpp_args=[r'-Ipycparser/utils/fake_libc_include', r'-ISDL/include/', r'-DSDL_MALLOC=', r'-DSDL_DECLSPEC=', r'-DSDL_ALLOC_SIZE2(a,b)=', r'-DSDL_ALLOC_SIZE(a)=', r'-U__GNUC__', r'-U__x86_64__'])  # type: ignore
v = FuncDefVisitor()
v.visit(ast)

header_begin = """#pragma once
// Autogenerated with ../gen.py

#include <SDL3/SDL.h>
#include <exception>
#include <string>
#include <unordered_map>
#include <memory>
#include <vector>

namespace SDL {

class Error : public std::exception
{
    const char* msg;
public:
    Error(const char* msg) : msg(msg) { }
    const char* what() const throw() { return msg; }
};

bool operator!(SDL_GUID id)
{
    for (size_t i = 0; i < 16; i++)
    {
        if (id.data[i] != 0) return false;
    }
    return true;
}

using Rect = SDL_Rect;
using FRect = SDL_FRect;
using Point = SDL_Point;
using FPoint = SDL_FPoint;

"""

header_end = """
}"""

with open("SDL++/SDL++.hpp", "w+") as f:
    f.write(header_begin + get_enums() + get_raw_ns(v.funcs) + get_classes(v.funcs) + get_extra_funcs(v.funcs) + header_end)
