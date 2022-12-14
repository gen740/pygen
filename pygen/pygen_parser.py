import copy
from typing import List

from clang.cindex import AccessSpecifier, Config, Cursor, CursorKind, TranslationUnit

from .component import Function, StructOrClass, Submodule


class Parser:
    """
    PyGen はヘッダーを解析し、pybind11 用の関数を自動で作り出すコードジェネレー
    タです。
    """

    def __init__(
        self, *, library_path: str | None = None, library_file: str | None = None
    ):
        self._funcitons: List[Function] = []
        self._submodules: List[Submodule] = []
        self._structs_and_classes: List[StructOrClass] = []
        self._hpp_includes: List[str] = []

        if library_file != None and library_path != None:
            raise ValueError(f"Both library_path and library_file cannot be set.")
        if not library_path is None:
            Config.set_library_path(library_path)
        if not library_file is None:
            Config.set_library_file(library_file)

    def _get_tu(self, source: str, lang: str = "c", flags=[]) -> TranslationUnit:
        if flags == None:
            flags = []
        args = list(flags)
        name = "t.c"
        if lang == "cpp":
            name = "t.cpp"
            # args.append("-std=c++11")
        if lang == "hpp":
            name = "t.hpp"
            # args.append("-std=c++11")
        return TranslationUnit.from_source(
            name,
            args,
            unsaved_files=[(name, source)],
            options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
        )

    def _extract_functions(self, cu: Cursor, namespace: List[str], module_name: str):
        """
        cu 以下にある関数を抽出する
        """
        for i in list(cu.get_children()):
            i: Cursor
            if i.kind == CursorKind.FUNCTION_DECL and i.is_definition():  # type: ignore
                func = Function()
                func.set_return_type(i.result_type.spelling)
                func.set_function_name(i.spelling, namespace)
                func.set_module(module_name)
                func.set_description(i.brief_comment or "")
                for j in list(i.get_children()):
                    j: Cursor
                    if j.kind == CursorKind.PARM_DECL:  # type: ignore
                        func.add_argument_type((j.spelling, j.type.spelling))
                self._funcitons.append(func)

    def _extract_struct_and_class(
        self, cu: Cursor, namespace: List[str], module_name: str
    ):
        """
        cu 以下にある構造体を抽出する
        """
        for i in list(cu.get_children()):
            i: Cursor
            # print(i.kind, i.spelling)
            if i.kind == CursorKind.STRUCT_DECL or i.kind == CursorKind.CLASS_DECL:  # type: ignore
                struct_or_class = StructOrClass()
                struct_or_class.set_name(i.spelling)
                struct_or_class.set_module(module_name)
                struct_or_class.set_namespace(namespace)
                struct_or_class.set_description(i.brief_comment or "")
                for j in list(i.get_children()):
                    j: Cursor
                    if j.kind == CursorKind.FIELD_DECL:  # type: ignore
                        # メンバー変数の抽出
                        struct_or_class.add_member(
                            j.spelling,
                            j.type.spelling,
                            j.brief_comment or "",
                            j.access_specifier == AccessSpecifier.PRIVATE,  # type: ignore
                        )
                    elif j.kind == CursorKind.CXX_METHOD:  # type: ignore
                        # メンバー関数の抽出
                        args = []
                        for k in list(j.get_children()):
                            if k.kind == CursorKind.PARM_DECL:  # type: ignore
                                args.append((k.spelling, k.type.spelling))
                        struct_or_class.add_member_func(
                            j.spelling,
                            j.result_type.spelling,
                            args,
                            j.brief_comment or "",
                            j.access_specifier == AccessSpecifier.PRIVATE,  # type: ignore
                        )
                self._structs_and_classes.append(struct_or_class)

    def add_hpp_includes(self, hpp: str):
        self._hpp_includes.append(hpp)

    def parse(self, source: str, lang: str = "cpp", flags=[]):
        root: Cursor = self._get_tu(source, lang, flags).cursor
        for i in list(root.get_children()):
            i: Cursor

            # 再起的に関数を抽出する。
            def visit(x: Cursor, namespace: List[str], module_name: str):
                if lang == "cpp":
                    self._extract_functions(x, namespace, module_name)
                elif lang == "hpp":  # ヘッダーでのみクラスを抽出する。
                    self._extract_struct_and_class(x, namespace, module_name)
                for i in list(x.get_children()):
                    i: Cursor
                    namespace_in = copy.copy(namespace)
                    if i.kind == CursorKind.NAMESPACE:  # type: ignore
                        submod = Submodule()
                        submod.set_name(i.spelling)
                        submod.set_description(i.brief_comment or "")
                        submod.set_parent(copy.copy(namespace_in))
                        if not submod in self._submodules:
                            self._submodules.append(submod)
                        namespace_in.append(i.spelling)
                        visit(i, namespace_in, submod.cpp_name)

            # トップレベルの Shell namespace を探す
            if i.kind == CursorKind.NAMESPACE and i.spelling == "Shell":  # type: ignore
                visit(i, ["Shell"], "Shell")

    def parse_from_file(self, filename: str, lang: str = "cpp", flags=[]):
        with open(filename, "r") as f:
            data = f.read()
        self.parse(data, lang, flags)

    def to_decl_string(self):
        return (
            "/* Function Declarations Start */\n"
            + "\n".join([i.to_decl_string() for i in self._funcitons] + [""])
            + "/* Function Declarations End */\n\n"
        )

    def to_submod_string(self):
        return (
            "\t/* Submodule Declarations Start */\n"
            + "\n".join(["\t" + i.to_pybind_string() for i in self._submodules] + [""])
            + "\t/* Submodule Declarations End */\n\n"
        )

    def to_export_string(self):
        return (
            "\t/* Function Export Start */\n"
            + "\n".join(["\t" + i.to_pybind_string() for i in self._funcitons] + [""])
            + "\t/* Function Export End */\n\n"
            "\t/* Structs and Classes Export Start */\n"
            + "\n".join(
                ["\t" + i.to_pybind_string() for i in self._structs_and_classes] + [""]
            )
            + "\t/* Structs and Classes Export End */\n\n"
        )

    def generate(self) -> str:
        """
        inline 関数を実装した、 header only なコードを自動生成する関数
        """
        return (
            "#pragma once\n\n"
            "#include <pybind11/cast.h>\n"
            "#include <pybind11/pybind11.h>\n"
            "#include <pybind11/pytypes.h>\n"
            "#include <pybind11/stl.h>\n\n"
            "/* Custom Header Include Start */\n"
            + "\n".join([f'#include "{i}"' for i in self._hpp_includes])
            + "/* Custom Header Include End */\n\n"
            f"{self.to_decl_string()}\n"
            "\n"
            "namespace PyGen {\n\n"
            "static inline void PyGenExport(pybind11::module_ Shell)\n"
            "{\n\n"
            f"{self.to_submod_string()}\n\n"
            f"{self.to_export_string()}\n\n"
            "};\n"
            "}"
        )

    def cpp_generate(self) -> str:
        """
        hpp_generate と対になる。 Export の関数の実装部分を自動生成するコード
        """
        return (
            '#include "pygen_generated.hpp"\n\n'
            "#include <pybind11/cast.h>\n"
            "#include <pybind11/pybind11.h>\n"
            "#include <pybind11/pytypes.h>\n"
            "#include <pybind11/stl.h>\n\n"
            "\n"
            f"{self.to_decl_string()}\n"
            "\n"
            "namespace PyGen {\n\n"
            "void PyGenExport(pybind11::module_ Shell)\n"
            "{\n\n"
            f"{self.to_submod_string()}\n\n"
            f"{self.to_export_string()}\n\n"
            "};\n"
            "}"
        )

    def hpp_generate(self) -> str:
        """
        Header で関数を宣言したりし実際に利用しやすいコードにする。
        """
        return (
            "#pragma once\n\n"
            "#include <pybind11/cast.h>\n"
            "#include <pybind11/pybind11.h>\n"
            "#include <pybind11/pytypes.h>\n"
            "#include <pybind11/stl.h>\n\n"
            "/* Custom Header Include Start */\n"
            + "\n".join([f'#include "{i}"' for i in self._hpp_includes])
            + "/* Custom Header Include End */\n\n"
            "namespace PyGen {\n\n"
            "extern void PyGenExport(pybind11::module_ Shell);\n\n"
            "}"
        )
