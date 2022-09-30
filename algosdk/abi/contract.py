import json
from typing import Dict, List, Union

from algosdk.abi.method import Method, get_method_by_name


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
        desc: str = None,
        networks: Dict[str, "NetworkInfo"] = None,
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
        return Contract(name=name, desc=desc, networks=networks, methods=method_list)

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

    def dictify(self) -> dict:
        return {"appID": self.app_id}

    @staticmethod
    def undictify(d: dict) -> "NetworkInfo":
        return NetworkInfo(app_id=d["appID"])
