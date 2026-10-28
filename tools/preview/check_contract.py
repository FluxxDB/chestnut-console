"""The preview's stand-in must not drift from milestone 2's contract (the Mac agent's ask).

    check_contract.py <stub yaml> <console yaml>... -- <M2 package yaml>...

Fails when:
  1. an entity the console reads or writes is missing from the stub or from M2's packages, or has a
     different entity type in either;
  2. the stub defines an entity M2's packages don't (or with a different type). Stub-only
     machinery (the Scenario select) is allowed.
M2 may define more (timers, schedule settings, sim knobs): the console doesn't use those.
"""
import re
import sys

import yaml

# Entity domains whose list items carry contract ids.
DOMAINS = ("sensor", "binary_sensor", "text_sensor", "number", "select", "switch", "button",
           "climate", "datetime")
STUB_ONLY = {"scenario"}


class Loader(yaml.SafeLoader):
    pass


def _any_tag(loader, suffix, node):
    # ESPHome tags (!lambda, !secret, !include, !extend...): keep the plain value.
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


Loader.add_multi_constructor("!", _any_tag)


def entities(path):
    with open(path) as f:
        doc = yaml.load(f, Loader=Loader) or {}
    found = {}
    for domain in DOMAINS:
        for item in doc.get(domain) or []:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                found[item["id"]] = domain
    return found


def main(argv):
    split = argv.index("--")
    stub_path, console_paths, m2_paths = argv[0], argv[1:split], argv[split + 1:]
    stub = entities(stub_path)
    m2 = {}
    for p in m2_paths:
        m2.update(entities(p))
    console_text = "".join(open(p).read() for p in console_paths)
    used = sorted(i for i in stub if re.search(rf"\b{re.escape(i)}\b", console_text))

    bad = []
    for i in used:
        if i not in m2:
            bad.append(f"console uses {i} ({stub[i]}), which M2 doesn't define")
        elif m2[i] != stub[i]:
            bad.append(f"console uses {i}: {stub[i]} in the stub, {m2[i]} in M2")
    for i, domain in sorted(stub.items()):
        if i in STUB_ONLY or i in used:
            continue
        if i not in m2:
            bad.append(f"stub defines {i} ({domain}), which M2 doesn't")
        elif m2[i] != domain:
            bad.append(f"stub {i} is a {domain}, M2's is a {m2[i]}")
    if bad:
        print("FAIL contract drift:\n  " + "\n  ".join(bad))
        return 1
    print(f"PASS contract: {len(used)} ids the console uses, {len(stub) - len(STUB_ONLY)} stub ids, all in M2")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
