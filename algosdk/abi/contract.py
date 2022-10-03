from collections import Counter
import json
from typing import Dict, List, Union

from algosdk.abi.method import (
    Method,
    get_method_by_name,
    _differ,
    _ddiffer,
)


class Contract:
    """
    Represents a ABI contract description.

    Args:
        name (string): name of the contract
        methods (list): list of Method objects
        desc (string, optional): description of the contract
        networks (dict, optional): information about the contract in a
            particular network, such as an app-id.
    """

    def __init__(
        self,
        name: str,
        methods: List[Method],
        desc: str | None = None,
        networks: Dict[str, "NetworkInfo"] | None = None,
        canonical: bool = False,
    ) -> None:
        self.name = name
        self.methods = methods
        self.desc = desc
        self.networks = networks if networks else {}
        self.canonical = canonical

    def __eq__(self, o: object) -> bool:
        """TODO: this is a very weak notion of equality. Does it make sense to keep it?"""
        if not isinstance(o, Contract):
            return False
        return (
            self.name == o.name
            and self.methods == o.methods
            and self.desc == o.desc
            and self.networks == o.networks
        )

    def _has_overloaded_methods(self):
        method_count = Counter(m["name"] for m in self.dictify()["methods"])
        if not method_count:
            return False

        return method_count.most_common(1)[0][1] > 1

    def __xor__(self, other: "Contract") -> dict | None:
        assert isinstance(
            other, Contract
        ), f"cannot take diff of Contract with {type(other)}"

        if self == other:
            return None

        meth_diff = None
        if self.methods != other.methods:
            if (
                self._has_overloaded_methods()
                or other._has_overloaded_methods()
            ):
                # TODO: have a more nuanced approach to diffing when have overloaded methods
                meth_diff = (
                    self.dictify()["methods"],
                    other.dictify()["methods"],
                )

            else:
                sdict = {m.name: m for m in self.methods}
                odict = {m.name: m for m in other.methods}
                s_only = sorted(sdict.keys() - odict.keys())
                both = sorted(sdict.keys() & odict.keys())
                o_only = sorted(odict.keys() - sdict.keys())

                meth_diff = [sdict[m] ^ odict[m] for m in both]
                meth_diff += [(sdict[m].dictify(), None) for m in s_only]
                meth_diff += [(None, odict[m].dictify()) for m in o_only]

        return {
            "name": _differ(self.name, other.name),
            "desc": _differ(self.desc, other.desc),
            "methods": meth_diff,
            "networks": _ddiffer(self.networks, other.networks),
        }

    def equivalent(self, other: "Contract") -> bool:
        if not isinstance(other, Contract):
            return False

        diff = self ^ other
        if not diff:
            return True

        if diff["methods"]:
            if len(self.methods) != len(other.methods):
                return False
            smethods = sorted(self.methods, key=lambda m: m.name)
            omethods = sorted(other.methods, key=lambda m: m.name)
            if any(
                map(
                    lambda x: not x[0].equivalent(x[1]),
                    zip(smethods, omethods),
                )
            ):
                return False

        return not diff["networks"]

    @staticmethod
    def from_json(resp: Union[str, bytes, bytearray]) -> "Contract":
        d = json.loads(resp)
        return Contract.undictify(d)

    def dictify(self) -> dict:
        d: dict = {}
        d["name"] = self.name
        meths = (
            [m.canonicalized() for m in self.methods]
            if self.canonical
            else self.methods
        )
        d["methods"] = [m.dictify() for m in meths]
        d["networks"] = {k: v.dictify() for k, v in self.networks.items()}
        if self.desc is not None:
            d["desc"] = self.desc

        if self.canonical:
            d["methods"]

            def method_sort(methods):
                return sorted(
                    methods,
                    key=lambda meth: (
                        meth["name"],
                        tuple(a["type"] for a in meth["args"]),
                    ),
                )

            d = {
                "name": d["name"],
                "desc": d.get("desc"),
                "methods": method_sort(d["methods"]),
                "networks": d["networks"],
            }
            if d["desc"] is None:
                del d["desc"]

        return d

    @staticmethod
    def undictify(d: dict) -> "Contract":
        name = d["name"]
        method_list = [Method.undictify(method) for method in d["methods"]]
        desc = d["desc"] if "desc" in d else None
        networks = d["networks"] if "networks" in d else {}
        for k, v in networks.items():
            networks[k] = NetworkInfo.undictify(v)
        return Contract(
            name=name, desc=desc, networks=networks, methods=method_list
        )

    def get_method_by_name(self, name: str) -> Method:
        return get_method_by_name(self.methods, name)


class NetworkInfo:
    """
    Represents network information.

    Args:
        app_id (int): application ID on a particular network
    """

    def __init__(self, app_id: int) -> None:
        self.app_id = app_id

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, NetworkInfo):
            return False
        return self.app_id == o.app_id

    def __xor__(self, other: "NetworkInfo") -> dict | None:
        assert isinstance(
            other, NetworkInfo
        ), f"cannot take diff of NetworkInfo with {type(other)}"

        if self == other:
            return None

        return {
            "appID": _differ(self.app_id, other.app_id),
        }

    def dictify(self) -> dict:
        return {"appID": self.app_id}

    @staticmethod
    def undictify(d: dict) -> "NetworkInfo":
        return NetworkInfo(app_id=d["appID"])
