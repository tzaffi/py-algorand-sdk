import copy
import json
from typing import List, Union

from Cryptodome.Hash import SHA512

from algosdk import abi, error


def _dict_if_can(x):
    if hasattr(x, "dictify"):
        return x.dictify()
    return x


def _mdifc(xs):
    return list(map(_dict_if_can, xs))


def _differ(x, y, dont_erase=False):
    return (
        _dict_if_can(x)
        if dont_erase
        else None
        if x == y
        else (_dict_if_can(x), _dict_if_can(y))
    )


def _type_assertion(o: object, name: str, t: type):
    assert isinstance(o, t), f"{name} only defined for {t} but got {type(o)}"


def _ldiffer(xs, ys):
    _type_assertion(xs, "xs", list)
    _type_assertion(ys, "ys", list)

    if xs == ys:
        return None

    if len(xs) == len(ys):
        return [x ^ ys[i] for i, x in enumerate(xs)]

    return (_mdifc(xs), _mdifc(ys))


def _ddiffer(xs, ys):
    _type_assertion(xs, "xs", dict)
    _type_assertion(ys, "ys", dict)

    if xs == ys:
        return None

    x_only_keys = xs.keys() - ys.keys()
    common_keys = xs.keys() & ys.keys()
    y_only_keys = ys.keys() - xs.keys()

    diff = {k: xs[k] ^ ys[k] for k in common_keys}
    for k in x_only_keys:
        diff[k] = (_dict_if_can(xs[k]), None)
    for k in y_only_keys:
        diff[k] = (None, _dict_if_can(ys[k]))

    return diff


class Method:
    """
    Represents a ABI method description.

    Args:
        name (string): name of the method
        args (list): list of Argument objects with type, name, and optional
        description
        returns (Returns): a Returns object with a type and optional description
        desc (string, optional): optional description of the method
    """

    def __init__(
        self,
        name: str,
        args: List["Argument"],
        returns: "Returns",
        desc: str | None = None,
        canonical: bool = False,
    ) -> None:
        self.name = name
        self.args = args
        self.desc = desc
        self.returns = returns
        # Calculate number of method calls passed in as arguments and
        # add one for this method call itself.
        txn_count = 1
        for arg in self.args:
            if abi.is_abi_transaction_type(arg.type):
                txn_count += 1
        self.txn_calls = txn_count
        self.canonical = canonical

    def canonicalized(self) -> "Method":
        m = copy.deepcopy(self)
        m.canonical = True
        return m

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, Method):
            return False
        return (
            self.name == o.name
            and self.args == o.args
            and self.returns == o.returns
            and self.desc == o.desc
            and self.txn_calls == o.txn_calls
        )

    def __xor__(self, other: "Method") -> dict | None:
        assert isinstance(
            other, Method
        ), f"cannot take diff of Method with {type(other)}"

        return (
            None
            if self == other
            else {
                "name": _differ(self.name, other.name, dont_erase=True),
                "desc": _differ(self.desc, other.desc),
                "args": _ldiffer(self.args, other.args),
                "returns": self.returns ^ other.returns,
                "txn_calls": _differ(self.txn_calls, other.txn_calls),
            }
        )

    def equivalent(self, other: "Method") -> bool:
        if not isinstance(other, Method):
            return False

        diff = self ^ other
        if not diff:
            return True

        if diff["returns"] or diff["txn_calls"]:
            return False

        if not isinstance(diff["name"], str):
            return False

        if len(self.args) != len(other.args):
            return False

        for i, arg in enumerate(self.args):
            if not arg.equivalent(other.args[i]):
                return False

        return True

    def get_signature(self) -> str:
        arg_string = ",".join(str(arg.type) for arg in self.args)
        ret_string = self.returns.type
        return "{}({}){}".format(self.name, arg_string, ret_string)

    def get_selector(self) -> bytes:
        """
        Returns the ABI method signature, which is the first four bytes of the
        SHA-512/256 hash of the method signature.

        Returns:
            bytes: first four bytes of the method signature hash
        """
        hash = SHA512.new(truncate="256")
        hash.update(self.get_signature().encode("utf-8"))
        return hash.digest()[:4]

    def get_txn_calls(self) -> int:
        """
        Returns the number of transactions needed to invoke this ABI method.
        """
        return self.txn_calls

    @staticmethod
    def _parse_string(s: str) -> list:
        # Parses a method signature into three tokens, returned as a list:
        # e.g. 'a(b,c)d' -> ['a', 'b,c', 'd']
        stack = []
        for i, char in enumerate(s):
            if char == "(":
                stack.append(i)
            elif char == ")":
                if not stack:
                    break
                left_index = stack.pop()
                if not stack:
                    return [s[:left_index], s[left_index + 1 : i], s[i + 1 :]]

        raise error.ABIEncodingError(
            "ABI method string has mismatched parentheses: {}".format(s)
        )

    @staticmethod
    def from_json(resp: Union[str, bytes, bytearray]) -> "Method":
        method_dict = json.loads(resp)
        return Method.undictify(method_dict)

    @staticmethod
    def from_signature(s: str) -> "Method":
        # Split string into tokens around outer parentheses.
        # The first token should always be the name of the method,
        # the second token should be the arguments as a tuple,
        # and the last token should be the return type (or void).
        tokens = Method._parse_string(s)
        argument_list = [
            Argument(t) for t in abi.TupleType._parse_tuple(tokens[1])
        ]
        return_type = Returns(tokens[-1])
        return Method(name=tokens[0], args=argument_list, returns=return_type)

    def dictify(self) -> dict:
        d = {}
        d["name"] = self.name
        d["args"] = [arg.dictify() for arg in self.args]
        d["returns"] = self.returns.dictify()
        if self.desc:
            d["desc"] = self.desc

        if self.canonical:
            d = {
                "name": d["name"],
                "desc": d.get("desc"),
                "args": d["args"],
                "returns": d["returns"],
            }
            if d["desc"] is None:
                del d["desc"]
        return d

    @staticmethod
    def undictify(d: dict) -> "Method":
        name = d["name"]
        arg_list = [Argument.undictify(arg) for arg in d["args"]]
        return_obj = Returns.undictify(d["returns"])
        desc = d["desc"] if "desc" in d else None
        return Method(name=name, args=arg_list, returns=return_obj, desc=desc)


def get_method_by_name(methods: List[Method], name: str) -> Method:
    methods_filtered = [method for method in methods if method.name == name]

    if len(methods_filtered) > 1:
        raise KeyError(
            "found {} methods with the same name {}".format(
                len(methods_filtered),
                ",".join(
                    [method.get_signature() for method in methods_filtered]
                ),
            )
        )

    if len(methods_filtered) == 0:
        raise KeyError("found 0 methods for {}".format(name))

    return methods_filtered[0]


class Argument:
    """
    Represents an argument for a ABI method

    Args:
        arg_type (string): ABI type or transaction string of the method argument
        name (string, optional): name of this method argument
        desc (string, optional): description of this method argument
    """

    def __init__(
        self, arg_type: str, name: str | None = None, desc: str | None = None
    ) -> None:
        if abi.is_abi_transaction_type(arg_type) or abi.is_abi_reference_type(
            arg_type
        ):
            self.type = arg_type
        else:
            # If the type cannot be parsed into an ABI type, it will error
            self.type = abi.ABIType.from_string(arg_type)
        self.name = name
        self.desc = desc

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, Argument):
            return False
        return (
            self.name == o.name and self.type == o.type and self.desc == o.desc
        )

    def __xor__(self, other: "Argument") -> dict | None:
        assert isinstance(
            other, Argument
        ), f"cannot take diff of Argument with {type(other)}"

        return (
            None
            if self == other
            else {
                "type": _differ(str(self.type), str(other.type)),
                "name": _differ(self.name, other.name),
                "desc": _differ(self.desc, other.desc),
            }
        )

    def equivalent(self, other: "Argument") -> bool:
        if not isinstance(other, Argument):
            return False

        return str(self.type) == str(other.type)

    def __str__(self) -> str:
        return str(self.type)

    def dictify(self) -> dict:
        d = {}
        d["type"] = str(self.type)
        if self.name:
            d["name"] = self.name
        if self.desc:
            d["desc"] = self.desc
        return d

    @staticmethod
    def undictify(d: dict) -> "Argument":
        return Argument(
            arg_type=d["type"],
            name=d["name"] if "name" in d else None,
            desc=d["desc"] if "desc" in d else None,
        )


class Returns:
    """
    Represents a return type for a ABI method

    Args:
        arg_type (string): ABI type of this return argument
        desc (string, optional): description of this return argument
    """

    # Represents a void return.
    VOID = "void"

    def __init__(self, arg_type: str, desc: str | None = None) -> None:
        if arg_type == "void":
            self.type = self.VOID
        else:
            # If the type cannot be parsed into an ABI type, it will error.
            self.type = abi.ABIType.from_string(arg_type)
        self.desc = desc

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, Returns):
            return False
        return self.type == o.type and self.desc == o.desc

    def __xor__(self, other: "Returns") -> dict | None:
        assert isinstance(
            other, Returns
        ), f"cannot take diff of Returns with {type(other)}"

        return (
            None
            if self == other
            else {
                "type": _differ(self.type, other.type),
                "desc": _differ(self.desc, other.desc),
            }
        )

    def equivalent(self, other: "Returns") -> bool:
        if not isinstance(other, Returns):
            return False

        return str(self.type) == str(other.type)

    def __str__(self) -> str:
        return str(self.type)

    def dictify(self) -> dict:
        d = {}
        d["type"] = str(self.type)
        if self.desc:
            d["desc"] = self.desc
        return d

    @staticmethod
    def undictify(d: dict) -> "Returns":
        return Returns(
            arg_type=d["type"], desc=d["desc"] if "desc" in d else None
        )
