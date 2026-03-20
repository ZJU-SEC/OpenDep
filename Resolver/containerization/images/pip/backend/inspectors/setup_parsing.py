from __future__ import annotations

import ast
import configparser
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ ships tomllib
    import tomli as tomllib


def _unparse(node: ast.AST) -> str:
    return ast.unparse(node).strip()


def _string_value(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Str):
        return node.s
    return None


def _split_multiline_values(raw_value: str) -> list[str]:
    return [line.strip() for line in raw_value.splitlines() if line.strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


@dataclass
class _DataFlow:
    from_: str
    to_: str
    condition: str = "*"
    status: str = "str"
    extra_info: ast.AST | str = "*"


class SetupPyDependencyVisitor(ast.NodeVisitor):
    def __init__(self, file_name: str) -> None:
        self.file_name = file_name
        self.flag_finish = 0
        self.flag_error = False
        self.flag_nodep = False
        self.keywords = ["install_requires", "tests_require", "setup_requires", "extras_require"]
        contents = Path(file_name).read_text(encoding="utf-8", errors="ignore")
        if not any(keyword in contents for keyword in self.keywords):
            self.flag_nodep = True
            self.end_dataflow: list[_DataFlow] = []
            return

        self.unresolved_names: list[str] = [f"original@{keyword}" for keyword in self.keywords]
        self.resolved_names: list[str] = []
        self.dataflow: list[_DataFlow] = []
        self.scope_if: list[str] = []
        self.flag_args = 0
        try:
            self.process(file_name)
        except Exception:
            self.flag_error = True
            self.end_dataflow = []
            return
        self.merge_dataflow()

    def merge_dataflow(self) -> None:
        keywords = [*self.keywords, "original"]
        end_dataflow: list[_DataFlow] = []

        def search(flows: list[_DataFlow], target: str, condition: str) -> list[dict[str, object]]:
            resolved: list[dict[str, object]] = []
            for flow in flows:
                if target != flow.from_:
                    continue
                if flow.status == "str":
                    if condition == "*":
                        resolved.append({"flow": flow, "condition": flow.condition})
                    else:
                        resolved.append({"flow": flow, "condition": f"{condition}@{flow.condition}"})
                else:
                    next_condition = flow.condition if condition == "*" else f"{condition}@{flow.condition}"
                    resolved.extend(search(flows, flow.to_, next_condition))
            return resolved

        filtered = [flow for flow in self.dataflow if flow.from_ != "*"]
        for flow in filtered:
            if flow.from_ not in keywords:
                continue
            if flow.status in {"str", "file"}:
                end_dataflow.append(flow)
                continue
            for nested in search(filtered, flow.to_, flow.condition):
                nested_flow = nested["flow"]
                if isinstance(nested_flow, _DataFlow) and nested_flow.status == "str":
                    end_dataflow.append(
                        _DataFlow(
                            from_=flow.from_,
                            to_=nested_flow.to_,
                            condition=str(nested["condition"]),
                            status="str",
                            extra_info=nested_flow.extra_info,
                        )
                    )
        self.end_dataflow = end_dataflow

    def process(self, file_name: str) -> None:
        self.remove_nodes: set[str] = set()
        self.process_deps(file_name)
        for removable in self.remove_nodes:
            if removable in self.unresolved_names:
                self.unresolved_names.remove(removable)

        if self.flag_args == 1:
            for keyword in self.keywords:
                original_name = f"original@{keyword}"
                if original_name in self.unresolved_names:
                    self.unresolved_names.remove(original_name)

        previous = list(self.unresolved_names)
        while True:
            self.remove_nodes = set()
            self.process_deps(file_name)
            for removable in self.remove_nodes:
                if removable in self.unresolved_names:
                    self.unresolved_names.remove(removable)
            if not self.unresolved_names or set(previous) == set(self.unresolved_names):
                break
            previous = list(self.unresolved_names)

    def process_deps(self, file_name: str) -> None:
        contents = Path(file_name).read_text(encoding="utf-8", errors="ignore")
        self.visit(ast.parse(contents))
        self.flag_finish = 1

    def _is_file_reference(self, node: ast.AST) -> bool:
        candidate = _string_value(node)
        if candidate is None:
            return False
        suffix = Path(candidate).suffix
        return suffix in {".txt", ".in", ".pip", ".toml", ".rst"}

    def _assign(self, value: ast.AST, from_scope: str, condition: str = "*", extra_key: ast.AST | str = "*") -> None:
        string_value = _string_value(value)
        if string_value is not None:
            self.dataflow.append(_DataFlow(from_=from_scope, to_=string_value, condition=condition, extra_info=extra_key))
            return

        if isinstance(value, ast.Name):
            self.dataflow.append(_DataFlow(from_=from_scope, to_=value.id, status="name", condition=condition))
            if value.id not in self.resolved_names:
                self.unresolved_names.append(f"{from_scope}@{value.id}")
            return

        if isinstance(value, (ast.List, ast.Tuple)):
            for entry in value.elts:
                self._assign(entry, from_scope, condition, extra_key=extra_key)
            return

        if isinstance(value, ast.Dict):
            for key_node, value_node in zip(value.keys, value.values):
                self._assign(value_node, from_scope, condition, extra_key=key_node or extra_key)
            return

        if isinstance(value, ast.Subscript):
            root = value.value
            if isinstance(root, ast.Name):
                self.dataflow.append(_DataFlow(from_=from_scope, to_=root.id, status="name", condition=condition))
                if root.id not in self.resolved_names:
                    self.unresolved_names.append(f"{from_scope}@{root.id}")
            elif isinstance(root, ast.Attribute):
                self._assign(root.value, from_scope, condition)
            elif isinstance(root, ast.Subscript):
                self._assign(root.value, from_scope, condition)
            return

        if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
            self._assign(value.left, from_scope, condition, extra_key=extra_key)
            self.dataflow.append(_DataFlow(from_=from_scope, to_=from_scope, status="name", condition=condition))
            self._assign(value.right, from_scope, condition, extra_key=extra_key)
            self.dataflow.append(_DataFlow(from_=from_scope, to_=from_scope, status="name", condition=condition))
            return

        if isinstance(value, ast.IfExp):
            test_repr = _unparse(value.test)
            self._assign(value.body, f"{from_scope}_if", extra_key=extra_key)
            self.dataflow.append(
                _DataFlow(from_=from_scope, to_=f"{from_scope}_if", status="name", condition=f"{condition}@{test_repr}")
            )
            self._assign(value.orelse, f"{from_scope}_orelse", extra_key=extra_key)
            self.dataflow.append(
                _DataFlow(
                    from_=from_scope,
                    to_=f"{from_scope}_orelse",
                    status="name",
                    condition=f"{condition}@not {test_repr}",
                )
            )
            return

        if isinstance(value, ast.Call):
            if isinstance(value.func, ast.Name) and value.func.id == "dict":
                for keyword in value.keywords:
                    self._assign(keyword.value, from_scope, condition, extra_key=extra_key)

            for argument in value.args:
                if self._is_file_reference(argument):
                    file_value = _string_value(argument)
                    if file_value is not None:
                        self.dataflow.append(_DataFlow(from_=from_scope, to_=file_value, status="file", condition=condition))
                else:
                    self._assign(argument, from_scope, condition, extra_key=extra_key)

            if isinstance(value.func, ast.Name):
                self.dataflow.append(_DataFlow(from_=from_scope, to_=value.func.id, status="func", condition=condition))
                if value.func.id not in self.resolved_names:
                    self.unresolved_names.append(f"{from_scope}@{value.func.id}")
            elif isinstance(value.func, ast.Attribute):
                self._assign(value.func.value, from_scope, condition, extra_key=extra_key)

    def visit_If(self, node: ast.If) -> None:
        test_repr = _unparse(node.test)
        self.scope_if.append(test_repr)
        for statement in node.body:
            self.visit(statement)
        self.scope_if.pop()

        self.scope_if.append(f"not {test_repr}")
        for statement in node.orelse:
            self.visit(statement)
        self.scope_if.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for statement in node.body:
            self.visit(statement)
            if self.flag_finish <= 0 or not isinstance(statement, ast.Return):
                continue
            for unresolved in list(self.unresolved_names):
                if unresolved.split("@", 1)[1] != node.name:
                    continue
                scope = unresolved.split("@", 1)[0]
                self._assign(statement.value, scope)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self.flag_finish <= 0 or len(node.targets) != 1:
            return
        target = node.targets[0]

        if isinstance(target, ast.Name):
            for unresolved in list(self.unresolved_names):
                if unresolved.split("@", 1)[1] != target.id:
                    continue
                scope = unresolved.split("@", 1)[0]
                self._assign(node.value, scope)
                self.remove_nodes.add(unresolved)
                self.resolved_names.append(target.id)

        if isinstance(target, ast.Subscript):
            target_root = target.value
            if isinstance(target_root, ast.Name):
                for unresolved in list(self.unresolved_names):
                    if unresolved.split("@", 1)[1] != target_root.id:
                        continue
                    scope = unresolved.split("@", 1)[0]
                    self._assign(node.value, scope)
                    self.remove_nodes.add(unresolved)
                    self.resolved_names.append(target_root.id)

                subscript_key = self._slice_value(target.slice)
                if subscript_key in self.keywords:
                    if isinstance(node.value, ast.Dict):
                        for value_node in node.value.values:
                            self._assign(value_node, subscript_key, "@".join(self.scope_if))
                    else:
                        self._assign(node.value, subscript_key, "@".join(self.scope_if))

            elif isinstance(target_root, ast.Subscript) and isinstance(target_root.value, ast.Name):
                for unresolved in list(self.unresolved_names):
                    if unresolved.split("@", 1)[1] != target_root.value.id:
                        continue
                    scope = unresolved.split("@", 1)[0]
                    self._assign(node.value, scope)
                    self.remove_nodes.add(unresolved)
                    self.resolved_names.append(target_root.value.id)

        if isinstance(node.value, ast.Call):
            for keyword in node.value.keywords:
                if keyword.arg not in self.keywords:
                    continue
                if isinstance(keyword.value, ast.Dict):
                    for value_node in keyword.value.values:
                        self._assign(value_node, keyword.arg, "@".join(self.scope_if))
                else:
                    self._assign(keyword.value, keyword.arg, "@".join(self.scope_if))

        if isinstance(node.value, ast.Dict):
            for key_node, value_node in zip(node.value.keys, node.value.values):
                key = _string_value(key_node)
                if key not in self.keywords:
                    continue
                if isinstance(value_node, ast.Dict):
                    for nested_value in value_node.values:
                        self._assign(nested_value, key, "@".join(self.scope_if))
                else:
                    self._assign(value_node, key, "@".join(self.scope_if))

    def visit_Call(self, node: ast.Call) -> None:
        if self.flag_finish == 0:
            for keyword in node.keywords:
                if keyword.arg not in self.keywords:
                    continue
                self.flag_args = 1
                if isinstance(keyword.value, ast.Dict):
                    for key_node, value_node in zip(keyword.value.keys, keyword.value.values):
                        self._assign(value_node, keyword.arg, "@".join(self.scope_if), extra_key=key_node or "*")
                else:
                    self._assign(keyword.value, keyword.arg, "@".join(self.scope_if))

        if self.flag_finish > 0 and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.attr in {"append", "extend", "update"}:
                for unresolved in list(self.unresolved_names):
                    if node.func.value.id != unresolved.split("@", 1)[1]:
                        continue
                    for argument in node.args:
                        self._assign(argument, node.func.value.id, "@".join(self.scope_if))

    def _slice_value(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Index):  # pragma: no cover - Python <3.9 compatibility
            return _string_value(node.value)
        return _string_value(node)


def parse_setup_py_file(file_path: str) -> list[str]:
    visitor = SetupPyDependencyVisitor(file_path)
    if visitor.flag_error or visitor.flag_nodep:
        return []

    dependencies: list[str] = []
    for flow in visitor.end_dataflow:
        if flow.from_ == "install_requires":
            dependencies.append(flow.to_)
        elif flow.from_ == "extras_require":
            extra_name = _string_value(flow.extra_info if isinstance(flow.extra_info, ast.AST) else None)
            if extra_name is None and isinstance(flow.extra_info, str) and flow.extra_info != "*":
                extra_name = flow.extra_info
            if extra_name is None:
                continue
            dependencies.append(f"{flow.to_} ; extra == '{extra_name}'")
    return _dedupe(dependencies)


def parse_setup_cfg_text(setup_cfg_text: str) -> list[str]:
    dependencies: list[str] = []
    config = configparser.ConfigParser()
    config.read_string(setup_cfg_text)

    if config.has_section("options"):
        install_requires = config.get("options", "install_requires", fallback="")
        dependencies.extend(_split_multiline_values(install_requires))

    if config.has_section("options.extras_require"):
        for extra_name, extra_value in config.items("options.extras_require"):
            for dependency in _split_multiline_values(extra_value):
                dependencies.append(f"{dependency} ; extra == '{extra_name}'")

    return _dedupe(dependencies)


def parse_pyproject_text(pyproject_text: str) -> list[str]:
    data = tomllib.loads(pyproject_text)
    dependencies: list[str] = []

    project = data.get("project")
    if isinstance(project, dict):
        for dependency in project.get("dependencies", []):
            if isinstance(dependency, str):
                dependencies.append(dependency)
        optional_dependencies = project.get("optional-dependencies", {})
        if isinstance(optional_dependencies, dict):
            for extra_name, values in optional_dependencies.items():
                if isinstance(values, list):
                    for dependency in values:
                        if isinstance(dependency, str):
                            dependencies.append(f"{dependency} ; extra == '{extra_name}'")

    tool = data.get("tool")
    if isinstance(tool, dict):
        poetry = tool.get("poetry")
        if isinstance(poetry, dict):
            poetry_dependencies = poetry.get("dependencies", {})
            poetry_extras = poetry.get("extras", {})
            extra_lookup: dict[str, list[str]] = {}
            if isinstance(poetry_extras, dict):
                for extra_name, names in poetry_extras.items():
                    if isinstance(names, list):
                        extra_lookup[extra_name] = [str(name) for name in names]

            if isinstance(poetry_dependencies, dict):
                for package_name, value in poetry_dependencies.items():
                    if package_name == "python":
                        continue
                    converted = _poetry_dependency_to_requirement(package_name, value)
                    if converted is None:
                        continue
                    if isinstance(value, dict) and value.get("optional") is True:
                        attached = False
                        for extra_name, names in extra_lookup.items():
                            if package_name in names:
                                dependencies.append(f"{converted} ; extra == '{extra_name}'")
                                attached = True
                        if attached:
                            continue
                    dependencies.append(converted)

    return _dedupe(dependencies)


def _poetry_dependency_to_requirement(package_name: str, value: object) -> str | None:
    if isinstance(value, str):
        return f"{package_name}{_normalize_poetry_version(value)}"
    if isinstance(value, dict):
        version = value.get("version")
        if isinstance(version, str):
            return f"{package_name}{_normalize_poetry_version(version)}"
    return None


def _normalize_poetry_version(version: str) -> str:
    stripped = version.strip()
    if not stripped or stripped == "*":
        return ""
    if stripped.startswith("^"):
        normalized = stripped.replace("^", "~=", 1)
    else:
        normalized = stripped

    comparison_prefixes = ("<", ">", "=", "!", "~")
    if not normalized.startswith(comparison_prefixes):
        normalized = f"=={normalized}"

    if normalized.startswith("==") and "." not in normalized[2:]:
        normalized = f"{normalized}.0"
    return normalized.replace("*", "")
