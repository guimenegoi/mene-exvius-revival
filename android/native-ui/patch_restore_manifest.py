"""Opt-in AndroidManifest text patch for the LAB restore picker Activity.

Requires a decoded manifest; it does not touch a production APK. Compile the
Activity into a separate DEX before packaging the patched binary manifest.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

ANDROID = "{http://schemas.android.com/apk/res/android}"
PACKAGE = "com.square_enix.android_googleplay.FFBEWW"
ACTIVITY = "com.mene.exvius.RestoreActivity"
MAIN = "android.intent.action.MAIN"
LAUNCHER = "android.intent.category.LAUNCHER"
ET.register_namespace("android", "http://schemas.android.com/apk/res/android")


def patch_manifest(source: bytes) -> bytes:
    doc = ET.fromstring(source)
    if doc.tag != "manifest" or doc.get("package") != PACKAGE:
        raise ValueError("Unexpected FFBE package in decoded manifest")
    app = doc.find("application")
    if app is None or app.find("activity") is None:
        raise ValueError("Missing application or existing launcher")
    for child in app.findall("activity"):
        if child.get(ANDROID + "name") == ACTIVITY:
            raise ValueError("Restore Activity is already registered")
    launchers = []
    for activity in app.findall("activity"):
        for intent in activity.findall("intent-filter"):
            actions = {item.get(ANDROID + "name") for item in intent.findall("action")}
            categories = {item.get(ANDROID + "name") for item in intent.findall("category")}
            if MAIN in actions and LAUNCHER in categories:
                launchers.append(activity)
    if len(launchers) != 1:
        raise ValueError("Expected exactly one existing launcher")
    activity = ET.SubElement(app, "activity", {
        ANDROID + "name": ACTIVITY,
        ANDROID + "exported": "true",
        ANDROID + "label": "FFBE • Restaurar save (LAB)",
        ANDROID + "screenOrientation": "portrait",
        ANDROID + "theme": "@android:style/Theme.Material.NoActionBar",
    })
    intent = ET.SubElement(activity, "intent-filter")
    ET.SubElement(intent, "action", {ANDROID + "name": MAIN})
    ET.SubElement(intent, "category", {ANDROID + "name": LAUNCHER})
    return ET.tostring(doc, encoding="utf-8", xml_declaration=True)
