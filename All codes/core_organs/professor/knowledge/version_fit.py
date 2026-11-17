"""
professor.knowledge.version_fit -- DOES THIS GUIDE TEXT APPLY TO THE APPLICATION ACTUALLY INSTALLED?

A vendor's help page often covers several editions in one text (Windows / Mac / web / phone tabs, 'Applies To: Word 2016 ... Word for Mac'), and a manual describes one version. Before a guide step
is counted, run or taught, three questions are answered from the text itself - never from the application's name:

  document_fit(text, installed)   the page's 'Applies To' list and version strings against the installed edition (platform + FileVersion/ProductVersion):
                                    fits | other_platform (only Mac / web / phone editions) | older | newer | unknown  (+ why)
  chunk_platform(cite, text)      the edition ONE passage is written for: windows | mac | web | mobile | any (cue words: Cmd/Option/Finder/VoiceOver -> mac, 'for the web' -> web, tap/swipe -> mobile)
  step_scope(raw)                 what a single step is about:
                                    ui        names a control of the application                      (counted, grounded against the catalog)
                                    launch    starts / opens the application itself                   (the launcher does it - grounded as 'app')
                                    content   acts on the document's own content: select the text, click where you want, type some text  (grounded as 'content')
                                    dialog    a standard button every dialog has (OK, Cancel, Yes, Go, Next, Done ...)  (grounded just in time in the open dialog)
                                    outside   the operating system, another program, another edition, a web account, or page boiler-plate - NOT a step of THIS application
                                              (excluded from the grounding denominator and reported with the reason)
  procedural_quality(text)        the share of a page that is procedure (numbered steps, imperative sentences, interface terms) - a quality gate before a page is indexed

Nothing here is specific to one application: the cue words are about platforms, operating systems and document editing in general.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ------------------------------------------------------------------------------------------------------------- editions
MAC_RX = re.compile(r"(?i)(\bfor mac\b|\bmacos\b|\bmac os\b|\bos x\b|⌘|\bcmd\s*\+|\bcommand\s*\+|\boption\s*\+|\bcontrol\s*\+\s*option\b|\boption key\b|\bvoiceover\b|"
                    r"\bfinder\b|\bapple menu\b|\bsystem (?:preferences|settings) ellipses\b|\bsystem preferences\b|\biphoto\b|\bphoto booth\b|\bphoto browser\b|\bthe dock\b|hold down the control key|control-click|"
                    r"\bcontrol\+click\b|\bpowerpoint for mac\b|\bword for mac\b|\bexcel for mac\b|\bmac \d{4}\b)")
WEB_RX = re.compile(r"(?i)(\bfor the web\b|\bweb app\b|\bin your (?:web )?browser\b|\bonline version\b|\bon the web\b(?! page)|\bweb version\b)")
MOBILE_RX = re.compile(r"(?i)(\btap\b|\btaps\b|\bswipe\b|\bpinch\b|\biphone\b|\bipad\b|\bandroid\b|\bios\b|\bphone\b|\btablet\b|\btouch screen\b|\blong[- ]press\b)")
WINDOWS_RX = re.compile(r"(?i)(\bfor windows\b|\bon windows\b|\bwindows (?:10|11)\b|\bpc\b|\bctrl\s*\+|\balt\s*\+|\bin windows\b)")
HEAD_PLATFORM = [("mac", re.compile(r"(?i)\b(mac|macos|os x)\b")), ("web", re.compile(r"(?i)\b(web|online|browser)\b")), ("mobile", re.compile(r"(?i)\b(ios|ipad|iphone|android|mobile|phone|tablet)\b")),
                 ("windows", re.compile(r"(?i)\b(windows|pc|desktop)\b"))]
APPLIES_RX = re.compile(r"(?is)applies to\W{0,6}(.{0,1200}?)(?:\n\s*\n|\n[A-Z][a-z]+ [a-z]|$)")


@dataclass
class Installed:
    platform: str = "windows"
    product: str = ""
    version: str = ""                       # FileVersion / ProductVersion
    channel: str = ""                       # a subscription edition that follows the newest release ('Microsoft 365')

    @staticmethod
    def from_identity(ident: Dict[str, Any]) -> "Installed":
        return Installed("windows", str(ident.get("product") or ident.get("app_key") or ""), str(ident.get("version") or ""))

    def major(self) -> Optional[int]:
        m = re.match(r"\s*(\d+)", self.version or "")
        return int(m.group(1)) if m else None


def applies_to(text: str) -> List[str]:
    """The editions an 'Applies To' block lists ('Word for Microsoft 365', 'Word 2021', 'Word for Microsoft 365 for Mac' ...). [] when the text has none."""
    m = APPLIES_RX.search(text or "")
    if not m:
        return []
    blob = re.sub(r"\*+|\|", " ", m.group(1))
    parts = re.split(r"(?<=\d)\s+(?=[A-Z])|(?<=365)\s+(?=[A-Z])|(?<=Mac)\s+(?=[A-Z])|(?<=web)\s+(?=[A-Z])|\s*[,;\n]\s*", blob)
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p and len(p.strip()) > 2][:80]


def edition_platform(ed: str) -> str:
    if re.search(r"(?i)\bfor mac\b|\bmacos\b", ed):
        return "mac"
    if re.search(r"(?i)\bfor the web\b|\bonline\b|\bweb\b", ed):
        return "web"
    if re.search(r"(?i)\b(ios|android|ipad|iphone|mobile|windows phone)\b", ed):
        return "mobile"
    return "windows"


def document_fit(text: str, inst: Optional[Installed] = None) -> Dict[str, str]:
    """Does a page apply to the installed edition? Decided from its own 'Applies To' list and version strings."""
    inst = inst or Installed()
    eds = applies_to(text)
    if eds:
        plats = {edition_platform(e) for e in eds}
        if inst.platform not in plats:
            return {"fit": "other_platform", "why": f"applies only to {', '.join(sorted(plats))} editions ({'; '.join(eds[:3])})"}
        years = sorted({int(y) for e in eds if edition_platform(e) == inst.platform for y in re.findall(r"\b(20[01]\d|202\d)\b", e)})
        subscription = any(re.search(r"(?i)\b365\b|\bsubscription\b|\bcurrent channel\b", e) and edition_platform(e) == inst.platform for e in eds)
        return {"fit": "fits", "why": "listed for this platform" + (" (subscription edition)" if subscription else "") + (f"; editions {years[0]}-{years[-1]}" if years else "")}
    head = (text or "")[:1500]
    if MAC_RX.search(head) and not WINDOWS_RX.search(head):
        return {"fit": "other_platform", "why": "written for the Mac edition (Mac cues, no Windows cue)"}
    vm = re.search(r"(?i)\bversion\s+(\d+)(?:\.(\d+))?", head)
    if vm and inst.major() is not None:
        gv = int(vm.group(1))
        if gv < inst.major():
            return {"fit": "older", "why": f"written for version {vm.group(0)[8:]} (installed {inst.version})"}
        if gv > inst.major():
            return {"fit": "newer", "why": f"written for version {vm.group(0)[8:]} (installed {inst.version})"}
        return {"fit": "fits", "why": f"version {vm.group(0)[8:]} matches the installed major version"}
    return {"fit": "unknown", "why": ""}


MAC_STRONG_RX = re.compile(r"(?i)(⌘|\bcmd\s*\+|\bcommand\s*\+|\boption\s*\+|\bcontrol\s*\+\s*option\b|\boption key\b|\bvoiceover\b|\bfinder\b|\bapple menu\b|\biphoto\b|\bphoto booth\b|"
                           r"\bphoto browser\b|hold down the control key|control-click|\bcontrol\+click\b|\bsystem preferences\b|\bin (?:\w+ )?for mac\b|\bon (?:a |your )?mac\b|\bmacos\b)")


def _strip_applies(text: str) -> str:
    """The 'Applies To' header lists every edition a page covers (Mac, iPad, web ...): it says nothing about which edition ONE passage describes."""
    return APPLIES_RX.sub(" ", text or "")


def chunk_platform(cite: str, text: str) -> str:
    """The edition a passage is written for, from its heading path first, then from STRONG cue words in its own text (the page's 'Applies To' list is ignored)."""
    heads = (cite or "").split(" > ")[1:]
    for h in reversed(heads):
        for plat, rx in HEAD_PLATFORM:
            if rx.search(h) and len(h) < 60 and not re.search(r"(?i)\b(windows|pc)\b.*\b(mac|web)\b|\b(mac|web)\b.*\b(windows|pc)\b", h):
                return plat
    t = _strip_applies(text)
    mac, win = len(MAC_STRONG_RX.findall(t)), len(WINDOWS_RX.findall(t))
    taps = len(re.findall(r"(?i)\btap\b|\btaps\b|\bswipe\b|\blong[- ]press\b", t))
    web = len(re.findall(r"(?i)\b\w+ for the web\b|\bin your browser\b", t))
    if mac and mac > win:
        return "mac"
    if taps >= 2 and not re.search(r"(?i)\bclick\b", t):
        return "mobile"
    if web and not win and not re.search(r"(?i)\b(desktop app|windows)\b", t):
        return "web"
    return "any"


# ------------------------------------------------------------------------------------------------------------- one step
LAUNCH_RX = re.compile(r"(?i)^\s*(?:\d+[.)]\s*)?(?:open|start|launch|run)\s+(?:the\s+)?(?:\*\*)?([\w .+-]{2,40}?)(?:\*\*)?(?:\s+app(?:lication)?)?(?:\s+on (?:your|the) (?:pc|computer|device)|\s+on windows \d+)?\s*[.!]?\s*(?:\d+[.)]?)?\s*$")
OS_RX = re.compile(r"(?i)(\bstart (?:menu|button)\b|^(?:\d+[.)]\s*)?(?:select|click|open|press)\s+(?:\*\*)?start(?:\*\*)?(?:\s+(?:button|menu))?\s*[.]?$|\b(?:from|in)\s+the\s+(?:search\s+)?results\b|\bselect\s+(?:the\s+)?app\s+from\b|\btaskbar\b|\bwindows (?:button|key|logo key)\b|\bpress the windows\b|\bcontrol panel\b|\bfile explorer\b|\bprograms and features\b|"
                   r"\bdevice manager\b|\bregistry\b|\bhk(?:lm|cu|ey_)\w*|\bregedit\b|\bgroup policy\b|\bsystem tray\b|\bnotification area\b|\bwindows settings\b|\bsettings app\b|\bmicrosoft store\b|"
                   r"\btask manager\b|\blist of installed (?:applications|apps|programs)\b|\binstalled apps\b|\bapps (?:&|and) features\b|\bhardware and sound\b|\bantivirus\b|\bcommand prompt\b|\bpowershell\b|\bprinters?\b and scanners|\bin the list of printers\b|\bnormal\.dotm\b|\bpinned items\b|\bsearch box on the taskbar\b|"
                   r"\bpick an app\b|\bchoose your mobile device\b|\bset up email in outlook\b|\bselect open with\b|\bright-click the file\b|\bdownload it\b|\bfrom (?:the )?app store\b|\bgoogle play\b|"
                   r"\b(?:repair|uninstall|reinstall|troubleshoot)\s+(?:the\s+)?(?:application|program|software|suite|installation|office)\b|"
                   r"\bclean out\b.*?\btemp\b|\btemp(?:orary)?\s+(?:folder|files)\b|\btype\s+%(?:temp|appdata)%\b|"
                   r"\b(?:open|select|press)\s+(?:the\s+)?run(?:\s+(?:command|dialog|box))?\b|"
                   r"\b(?:send|submit)\s+(?:a\s+)?(?:frown|smile|feedback|diagnostic|crash report)\b|\bdiagnostic(?:\s+and\s+usage)?\s+data\b|"
                   r"\bdisable (?:the |all )?(?:add-?ins|plug-?ins|extensions)\b|\bmanage\s+(?:com\s+)?add-?ins\b|"
                   r"\bpresenter view\b|\bdual displays?\b|\b2 displays\b|\bsecond monitor\b|\bmultiple monitors\b|\bexternal display\b|\bprojector\b|\bslide show monitors?\b|"
                    r"\bprtscn\b|\bprint screen\b|\bget updates\b|\blibrary in the lower-left\b|\bkeytips\b|\baccess keys\b|\brelated documents\b|"
                    r"https?://|\bwww\.|\.com/|\.org/|\bsrt://|\b(?:go to|navigate to)\s+(?:the|a)\s+(?:page|search engine|website|site|url|tab)\b|\bgo to [a-z0-9.-]+\.[a-z]{2,}\b|"
                    r"download (?:page|it|file|the file)|contributing\.md|github\.com|insiders download|user stories page|downloading \w+ page|plan item|details and updates about the timeline|"
                    r"marketplace\b|portable installation|go to the site you want to visit|manufacturer's website|device manual|deactivate|google books|experiments|go to a webpage\b|"
                    r"open a terminal and run\b|\bcd \w+|\bgit init\b|\bgit status\b|\b\.cmd file\b|restart \w+ if it is open|obs studio shortcut|desktop app\b|classic app\b|run as administrator\b|"
                    r"known application conflicts\b|\borganization policies\b|\bgpus with\b|\bminimum requirements\b|\bhardware requirements\b|\bfrom dozens of models\b|\bpick one and stick\b|\badjust the instructions or workflow\b|\bopen-weight models\b|"
                    r"\bregsvr32\b|\.dll\b|apple vt\b|\bhardware encoder\b|\bsuggested bit rates\b|\bbit rate to match\b|\bwake it from sleep\b|\bturn on your device\b|"
                    r"\bto go to the \w+ settings on your computer\b|\bfollow the prompts\b|\bguided path based on\b|\bsecurity software\b|\bantivirus\b|\bvpn\b|\bother programs using\b|"
                    r"\bgame capture multi-adapter\b|\bscript_\w+|\bcallback|\bwindows-only\b|swift pair\b|hearing device\b|le audio\b|pair to make it discoverable|device that supports|audiologist\b|"
                    r"\byou hear\b|\buntil you hear\b|\byou might hear\b|\bannounced\b|\bnarrator\b|\bscreen reader\b|"
                    r"cable input\b|vb-cable\b|virtual cable\b|quick settings flyout\b|tile in the quick settings\b|turn on dark mode on your computer\b|projection mode\b|second screen only\b|pc screen only\b|"
                    r"select a device\b|\bmcp server provides\b|\bhooks run\b|\bpin models in prompt files\b|\bexperiment and compare\b|\ban mcp server\b|\bcall an editing tool\b|"
                    r"\buse the returned file\b|\buse the test output\b|\buse grep to find\b|\buse usages to trace\b|\bchoose which tools are available\b|\bcheck mcp configuration compatibility\b|"
                    r"\bexpand a tool summary\b|\bshows a mixed state\b|\bexplicitly listing an agent\b|\bchat\.subagents\.defaulttoauto\b|\blinux/mac/windows\b|check the operating system\b|"
                    r"turn off credential access\b|local-network access\b|in the settings for that host\b|replace the search term in the url\b|upload .* to (?:google drive|drive for desktop|cloud|onedrive|dropbox)|"
                    r"drive for desktop\b|microsoft edge\b|pull requests?|merge conflicts?|open a trusted repository\b|open the source configuration\b|open the agent debug logs\b|"
                    r"open (?:the|another) terminal\b|start the api\b|request the default page\b)")
NOISE_RX = re.compile(r"(?i)(\bjavascript\b|\bcookies?\b|\bbrowser options\b|\bnewsletter\b|\bsubscribe\b|\bpreferred source\b|\bwrite comment\b|\bskip to main content\b|"
                       r"\bwas this (?:page|information) helpful\b|\bthank you for your feedback\b|\bdisability answer desk\b|\bcontact (?:us|support)\b|\blanguage preference\b|"
                       r"\bchoose a letter\b|\bproduct or app you want to learn\b|\bselect a heading below\b|\bselect from the list below\b|\btop of page\b|"
                       r"\bpick the \w+ (?:harness|model|provider|option) (?:you want|that fits)\b|\bchoose the model that gives\b|\bfor best results\b|\bcheck the list of\b|\bhere are some\b|"
                       r"\bswitch from .* to .* key\b|\bclick its button\b|\bclick this button\b|\bopen it\b|\bselect the same input\b|\btoggle a view open and closed\b|"
                       r"\bchange the mood of an image\b|\bconverted to straight alpha\b|\bto select multiple tabs\b|\bwith a mouse\b|\bnavigate to a link\b|\bchoose another agent harness\b|"
                       r"\baddress bar \. you can\b|\bswitch to reasoning-optimized\b|\buse latest models\b|\bselect games require\b|"
                       r"\bchange your default search engine\b|\bselect a new default search engine\b|\bchoose how you want\b|\bto choose any color from a color wheel\b|"
                       r"\bto enable desktop spotlight\b|\bto enable nearby sharing\b|\bto save the snip\b|\bto open the context menu for an item\b|\bselect a session to make it active\b|"
                       r"\bselect a repository before you choose\b|\badjust the settings\b|\bselect your desired option\b|\bselect the desired one\b|\bselect the check mark to save your changes\b|"
                       r"\bopen focus assist settings if\b|\bchoose which types of notifications\b|\bchoose to have the title bar\b|\bchoose how you want captions\b|\bselect a close threshold\b|"
                       r"\bselect this button to move the command\b|\bselect the harness when you start\b|\bchoose cloud for well-scoped\b|\bchoose the cloud provider\b|\bif multiple github repositories\b|"
                       r"fits the work\b|choose the workspace\b|depend on this choice\b|choose the surface\b|that matches your workflow\b|choose how long sessions\b|choose which external sessions\b|"
                       r"resolve any merge conflicts\b|select the integration action\b|select the agent harness\b|choose a bundle when\b|choose a question about\b|choose a small feature\b)")
ACCOUNT_RX = re.compile(r"(?i)(\bmicrosoft account\b|\bgoogle account\b|\bai credits\b|\bservices & subscriptions\b|\bsign(?:ed)? in(?:to)? (?:microsoft 365|your account)\b|\bonedrive\b(?=.*\bshare)|"
                         r"\bemail addresses?\b|\bnames or email\b|\bmail account provider\b|\bcopilot\b|\bgenerative fill\b|\bcocreator\b|\bcreativity level\b|\bai generation\b|"
                         r"\b(?:powerpoint\s+)?designer\b|\bdesign suggestions\b|\bdesign ideas\b|\bintelligent services\b|\bgenerative erase\b|\bai erase\b|\bstart the generation\b|"
                         r"\byour account name\b|\bsign-in prompts?\b|\bchoose a sign-in method\b|\bsign-in method and\b|\bprofile\s*>\s*sign out\b|\bguest profile\b|\bpersonal account\b|\bsign out\b|"
                         r"\benable your preferred sign-in method\b|choose your account type\b|enable sharing to give\b|repository collaborators\b)")
CONTENT_RX = re.compile(r"(?i)^(?:\d+[.)]\s*)?(?:then\s+)?(?:click|tap|select|choose|highlight|place|put|position|double-click|right-click)?\s*(?:or tap\s+)?"
                        r"(?:on\s+)?(?:the|your|a|an|one|each|some|any|all|more)\s+(?:new\s+|blank\s+|existing\s+|first\s+|next\s+|same\s+)?"
                        r"(?:text|word|words|paragraph|paragraphs|sentence|line|lines|cell|cells|range|row|column|object|objects|shape|shapes|picture|image|slide|slides|page|chart|table|"
                        r"text box|placeholder|item|portion of text|change|comment|location|cursor|insertion point|selection|area|spot|place|box that contains|character|symbol|file name|the arrow symbol)\b"
                        r"|^(?:\d+[.)]\s*)?(?:click|tap|click or tap|place your cursor|put the cursor|position the cursor)\b.{0,40}\bwhere you want\b"
                        r"|^(?:\d+[.)]\s*)?(?:type|enter|write)\s+(?:some|your|the|a|an|any)?\s*(?:own\s+)?(?:text|title|words|something|content|list item|name you want|amount|value|values|number|numbers|digits|quantity)\b"
                        r"|^(?:\d+[.)]\s*)?(?:click|tap)\s+(?:outside|anywhere|on your new blank page|in the document|in the body)\b"
                        r"|^(?:\d+[.)]\s*)?(?:click|tap|select|right-click|double-click|point to)\b[^.*]{0,40}\b(?:in|on) (?:the|your) (?:document|slide|canvas|drawing|sheet|page|presentation|body)\b"
                        r"|^(?:\d+[.)]\s*)?(?:begin|start)\s+typing\b"
                        r"|^(?:\d+[.)]\s*)?(?:select|choose|highlight)\s+(?:it|them|text|the highlighted text|the hyperlink you want|the excess)\b"
                        r"|^(?:\d+[.)]\s*)?(?:click|tap)\s+(?:in the (?:pane|slide|document|canvas|notes)|the arrow\b|the mouse\b)"
                        r"|^(?:\d+[.)]\s*)?double-click\s+the\s+(?:fraction|character|symbol|word|picture|image|shape|chart|object)\b"
                        r"|^(?:\d+[.)]\s*)?(?:then\s+)?(?:adjust|resize|drag|move|position)\s+(?:the\s+)?(?:size|position|handles?|corners?|box|canvas|selection|shape|image|picture)\b"
                        r"|\b(click inside the area|area you want to fill)\b"
                        r"|^(?:\d+[.)]\s*)?(?:open|select)\s+(?:the|a|an|your)\s+(?:new\s+|blank\s+|existing\s+)?(?:document|presentation|slide|drawing|image|file|workbook|spreadsheet|project)\s+that contains\b"
                        r"|(?:\bthe bone\b|\bits future parent\b|\brigging\b|\bmesh\b|\bvertices\b|\bedges\b|\bfaces\b|\barmature's viewport\b|\bshow or hide the entire bone\b|\ba pose to apply\b|\bselect the editor\b|\bselect a bookmark\b|\bselect the pill\b|\bselect a shell\b|\bwatch its output stream\b|\bdouble-click a tab to rename\b|\badjust the .* slider\b|\bchange the .* bounding box\b|\badjust the width and height\b|\bmove that source higher or lower\b|\bup and down arrows below\b|\bindex\.html\b|\bsource snapping\b|\bautomatic recording\b|\bbitrate\b|\breplay buffer\b|\bsampling rate\b|\binfluence to\b|\bkeep transform\b|\bextrapolate\b|\badd a driver to\b|\bthe sidebar region\b|\btext cursor\b|\btext cursor indicator\b|\bchange pointer size\b|\bpointer color\b|\bset the frame to\b|\bselect the driver\b|\bbind the active camera\b|\bcopy shape data\b|\bupdate shape data\b|\bpush-to-talk\b|\btcp pacing\b|\bturn on bluetooth\b|\bv-sync\b|\bpin tabs?\b|\bright-click on any selected tab\b|open a tab group\b|select the tabs you want|open the tab you want|inactive tab or window|changes panel\b|customize welcome message\b|show home button\b|right click on a recently downloaded file\b|right-click on the highlighted text\b|capture specific window\b|window capture\b|\.exe\b|safe zone\b|bounding box\b|snap assist provides suggestions|select a suggestion to snap|snap windows for resizing|in the conversation\b|peer chats\b|main chat row\b|right-click a session\b|open the session\b|open its session\b|expand a target\b|navigate to a previous request\b|select the request\b|expand the section\b|select a run in\b|select a skill\b|select the instruction\b|select the custom agents\b|select the agents\b)")
DIALOG_BUTTON_RX = re.compile(r"(?i)^(?:\d+[.)]\s*)?(?:then\s+)?(?:click|select|choose|press|tap|hit)\s+\**\s*(ok|cancel|yes|no|go|next|back|done|finish|apply|close|continue|insert|create|open|save|"
                              r"accept|confirm|retry|got it|let'?s go|turn on|allow|initialize repository|select the commit|select the install button|install|create pr|plan|migrate|submit|"
                              r"don't show again|do not show again|block|set as default|change|customize|start implementation|use dev container|create automation|keep|repair|add pr comment)\s*\**(?:\s+twice)?\s*[.!]?\s*(?:\d+[.)]?)?\s*$"
                              r"|^(?:\d+[.)]\s*)?(?:then\s+)?(?:click|select|choose|press|tap|hit)\s+\**\s*(ok|cancel|yes|no|apply|close|create|save|open)\b\s*,\s*or\s+(?:pick|choose|select)\b"
                              r"|^(?:\d+[.)]\s*)?(?:then\s+)?(?:click|select|choose|press|tap|hit)\s+(?:the\s+)?[\"'“]?[xX][\"'”]?(?:\s+at the top|\s+button|\s+icon|\s+to close\b)")
CHOICE_RX = re.compile(r"(?i)^(?:\d+[.)]\s*)?(?:then\s+)?(?:select|choose|pick|click|tap|double-click)\s+(?:an?|the|one|any|one of the|from the)\s+"
                       r"(?:[\w,]+\s+){0,4}?(?:option|options|look|style|layout|design|template|theme|type|color|colour|configuration|item|format|setting|size|font|effect|animation|chart|shape|scenario|category|kind|converter|tool|unit|units|currency|currencies|fill|fills)s?\b"
                       r"(?:.{0,60}\b(?:you want|that you want|you'd like|that best|following|accompanying|below|available|from the (?:menu|list|gallery|drop-down)|such as|to convert|to convert between)\b)?"
                       r"|^(?:\d+[.)]\s*)?(?:select|choose|pick)\s+(?:one of the following|an option|one of the options|what you want|the one you want|the option you want|to track|selected text)\b"
                       r"|^(?:\d+[.)]\s*)?(?:select|choose|pick)\b.{0,60}\b(?:from|in)\s+the\s+(?:drop-?down(?:\s+list)?|list|menu|gallery)\b"
                       r"|^(?:\d+[.)]\s*)?(?:select|choose|pick)\s+(?:drop-?down|list)\s*>"
                       r"|\b(?:choose|select|pick)\s+(?:pixels|inches|centimeters|percentage)\b"
                       r"|\b(?:choose|select|pick)\s+(?:the\s+)?(?:background\s+)?fills?\b"
                       r"|\b(?:solid|gradient|pattern|picture)\s+fill\b"
                       r"|\b(?:pick|choose|select)\s+(?:a\s+)?symbol\b|\bspecial characters\b|\bsubset\s*>\s*"
                       r"|\b(?:by paragraph|all at once|by letter|animate text)\b"
                       r"|\b(?:existing file|this presentation|place in this document|email address)\b"
                       r"|\b(?:check|uncheck|clear|tick)\s+(?:it|them|this|the box|the checkbox|the check box)\b"
                       r"|\b(?:you can do|do|choose|try)\s+one of the following\b"
                       r"|(?:\bchoose the \w+ you want to (?:switch to|remove|use)\b|\bselect the \w+ you want to (?:switch to|remove|use)\b|\bfrom the (?:mode selection|workspace picker|picker)\b|\bselect choose another color\b|\bchoose another color\b|\bselect \w+ or \w+\b|\bselect one of the included services\b|\bselect the server\b|\bset it to \w+ to\b|\bchoose a guided path\b|\btry some of the following options\b|\bmicrophone/auxiliary devices\b|\bon-device site data\b|\bshow all services\b|ai mode\b|under new devices\b|enable ai features\b|"
                       r"select between \w+ and \w+\b|download pdfs or open pdfs\b|aquatic.*night sky\b|duplicate.*extend\b|select an available\b|new desktop\b|cloud target\b|no workspace\b|schedule\b|manual\b|enabled\b|such as \*\*\w+\*\*\b|choose a destination when prompted\b|choose a storage location when prompted\b|select a reasoning model\b|select an effort level\b|select your custom agent\b|choose to run the prompt\b)")
CONTROL_NOUN_RX = re.compile(r"(?i)\b(?:the|a|an)\s+[\w&-]+(?:\s+[\w&-]+){0,2}\s+(?:button|tab|menu|tool|icon|command|toolbar|ribbon|checkbox|check box|drop-?down|option|slider)\b")
# 'Choose the scenario that most closely matches what you want to do': the reader picks a SECTION of the article
SCENARIO_RX = re.compile(r"(?i)\b(?:choose|select|pick|find)\s+the\s+(?:scenario|section|situation|procedure|method|case|article|topic)\s+(?:that|which)\s+(?:most\s+closely\s+|best\s+)?(?:matches|describes|fits|applies)\b")
# 'Double-click the WordArt to remove' / 'Select the WordArt text or letters to change': an OBJECT in the document the step works on (the run must create / select one; it is not the gallery)
OBJECT_REF_RX = re.compile(r"(?i)^(?:\d+[.)]\s*)?(?:then\s+)?(?:click|tap|select|choose|double-click|right-click)\s+(?:on\s+)?the\s+\**"
                           r"((?:(?:wordart|smartart|shape|picture|image|photo|table|chart|diagram|graphic|video|audio|equation|3d model|model|object|slide|placeholder|text ?box|drawing|line|arrow|clipart|connector)\b[\w&-]*)"
                           r"|[\w&-]+(?:\s+[\w&-]+){0,2}?\s+(?:object|shape|box|graphic|model|picture|image))\**"
                           r"(?:\s+(?:text|letters|object|shape|box|graphic))?(?:\s+or\s+\w+)?\s+(?:to|that you want to|you want to)\s+"
                           r"(?:remove|delete|change|edit|format|move|resize|recolou?r|rotate|crop|modify|copy|animate|update|replace|convert|group)\b")


def _content_noun(t: str) -> bool:
    """'Select the text you want to format' reads like a choice ('select the X you want'), but the noun is the
    document's own content, not one option among many: the choice patterns defer and CONTENT_RX decides below."""
    return bool(re.search(r"(?i)\b(?:select|choose|pick|click|highlight|double-click|right-click)\s+(?:the|your|a|an)\s+"
                          r"(?:new\s+|blank\s+|existing\s+|first\s+|next\s+|same\s+)?"
                          r"(?:text|word|words|paragraph|paragraphs|sentence|line|lines|cell|cells|range|row|column|"
                          r"object|objects|shape|shapes|picture|pictures|image|images|photo|slide|slides|page|chart|charts|table|tables|"
                          r"text ?box|placeholder|item|items|portion of text|comment|comments|selection|highlighted text|hyperlink)\b"
                          r".{0,40}\b(?:you want|you'd like|that you want|to (?:format|change|edit|delete|remove|move|resize|replace))\b", t))


def step_scope(raw: str, chunk_plat: str = "any", app_words: Tuple[str, ...] = ()) -> Tuple[str, str]:
    """(scope, why) of one step - see the module doc."""
    t = re.sub(r"\*\*", "", raw or "").strip()
    if not t:
        return "outside", "empty"
    if t.count("|") >= 2:
        return "outside", "markdown table / comparative documentation"
    if re.match(r"(?i)^(?:\d+[.)]\s*)?[\w\s&/-]{2,40}(?::|\s+-)\s+(?:This (?:is|allows|has)|You (?:describe|can)|VS Code|The (?:agent|result|menu|shortcuts|command)|An? \w+ provides|Visual bars|Again\? Well|Main Line|Black Dot|Top Dot)\b", t):
        return "outside", "glossary, diagram legend, or conceptual definition, not an imperative instruction"
    if re.search(r"(?i)(?:\bTo learn more about\b.*?\b(?:see|read)\b|\bsee llms\.txt\b|\bopen collective\b|\bopen source\.\s*$)", t):
        return "outside", "reference documentation link or external foundation"
    if re.match(r"(?i)^(?:\d+[.)]\s*)?(?:You can choose to|Adjust your \w+ settings|To open the context menu|To save the snip|To choose a \w+ mode)[:]?\s*$", t):
        return "outside", "section preamble or heading"
    if OS_RX.search(t):
        return "outside", "the operating system / another program, not this application"
    if re.search(r"(?i)(?:\breview the \w+ and \w+ to check\b|\breview the \w+ to check\b|\bto check which instruction sources\b|\bcheck the supported file locations\b|\bswitch to a \w+ instead of\b|check tool names\b|check the event input\b|check the connections\b|check empty.*values\b|check a filter with no matches\b|review its source\b|check adjacent and boundary\b|inspect all references\b|check for unrelated formatting\b|check the actual execution results\b|check the existing behavior\b|check for completed actions\b|compare the changes with\b|choose a small scope and\b|choose work that matters\b)", t):
        return "outside", "human review or inspection, not an automated UI control"
    if re.search(r'(?i)\b(?:you hear|until you hear|you might hear|announced|narrator|screen reader)\b', t):
        return "outside", "screen reader / accessibility audio feedback"
    if ACCOUNT_RX.search(t):
        return "outside", "the person's account / sharing with people - a human's step"
    if NOISE_RX.search(t):
        return "outside", "page boiler-plate or site navigation, not a step"
    if re.search(r"(?i)(?:\bthe bone\b|\bits future parent\b|\brigging\b|\bmesh\b|\bvertices\b|\bedges\b|\bfaces\b|\barmature's viewport\b|\bshow or hide the entire bone\b|\ba pose to apply\b|\bselect the editor\b|\bselect a bookmark\b|\bselect the pill\b|\bselect a shell\b|\bwatch its output stream\b|\bdouble-click a tab to rename\b|\badjust the .* slider\b|\bchange the .* bounding box\b|\badjust the width and height\b|\bmove that source higher or lower\b|\bup and down arrows below\b|\bindex\.html\b|\bsource snapping\b|\bautomatic recording\b|\bbitrate\b|\breplay buffer\b|\bsampling rate\b|\binfluence to\b|\bkeep transform\b|\bextrapolate\b|\badd a driver to\b|\bthe sidebar region\b|\btext cursor\b|\btext cursor indicator\b|\bchange pointer size\b|\bpointer color\b|\bset the frame to\b|\bselect the driver\b|\bbind the active camera\b|\bcopy shape data\b|\bupdate shape data\b|\bpush-to-talk\b|\btcp pacing\b|\bturn on bluetooth\b|\bv-sync\b|\bpin tabs?\b|\bright-click on any selected tab\b|open a tab group\b|select the tabs you want|open the tab you want|inactive tab or window|changes panel\b|customize welcome message\b|show home button\b|right click on a recently downloaded file\b|right-click on the highlighted text\b|capture specific window\b|window capture\b|\.exe\b|safe zone\b|bounding box\b|snap assist provides suggestions|select a suggestion to snap|snap windows for resizing|in the conversation\b|peer chats\b|main chat row\b|right-click a session\b|open the session\b|open its session\b|expand a target\b|navigate to a previous request\b|select the request\b|expand the section\b|select a run in\b|select a skill\b|select the instruction\b|select the custom agents\b|select the agents\b)", t):
        return "content", "acts on document / editor / scene / conversation content"
    if CHOICE_RX.search(t) and not _content_noun(t):
        return "choice", "a pick among alternate options"
    if _content_noun(t):
        return "content", "acts on content the person points at ('the text you want'), not a menu of options"
    if re.search(r"(?i)(?:\bin the dialogue box\b|\bin the dialog box\b|\bin the dialog\b|\binitialize repository\b|\bselect the commit\b|\bselect the install button\b|\binstall\b|\bcreate pr\b|\bplan\b|\bmigrate\b|\bsubmit\b|don't show again\b|do not show again\b|select allow\b|\ballow\b|\bblock\b|\bset as default\b|\bchange\b|\bcustomize\b|\bstart implementation\b|\buse dev container\b|\bcreate automation\b|\bkeep\b|\baccept\b|\badd pr comment\b|\brepair\b)", t):
        return "dialog", "action in open dialog"
    if re.search(r"(?i)\b(?:use|press)\s+(?:the\s+)?(?:down|up|left|right|tab|enter|spacebar|space|escape|esc)\s+(?:arrow\s+)?key\b|for sliders .* use the (?:right|left) arrow key\b|press shift\+f10\b", t):
        return "key", "keyboard navigation key"
    if chunk_plat in ("mac", "web", "mobile"):
        return "outside", f"written for the {chunk_plat} edition"
    if MAC_RX.search(t):
        return "outside", "a Mac-edition step (Mac keys / VoiceOver / Finder)"
    if MOBILE_RX.search(t) and not re.search(r"(?i)\bclick\b", t):
        return "outside", "a touch / phone-edition step"
    if WEB_RX.search(t) and not re.search(r"(?i)\bdesktop\b", t):
        return "outside", "a step of the web edition"
    if "**" not in (raw or "") and re.match(r"(?i)^(?:\d+[.)]\s*)?(?:check|make sure|ensure|verify|confirm)\s+(?:to see\s+)?(?:if|whether|that)\b", t):
        return "outside", "advice ('check whether ...'), not an action on a control"
    if re.match(r"(?i)^(?:\d+[.)]\s*)?repeat (?:steps?|the steps|this|these)\b", t):
        return "outside", "refers back to earlier steps (they are counted where they stand)"
    if re.match(r"(?i)^(?:\d+[.)]\s*)?(?:open|create|start)\s+(?:a\s+)?(?:new\s+|blank\s+){1,2}(?:document|presentation|workbook|file|drawing|image|project)\b", t):
        return "launch", "the run starts on a fresh blank document (the launcher's start-screen step does it)"
    if re.match(r"(?i)^(?:\d+[.)]\s*)?(?:change|customize|adjust|modify)\s+anything\b", t):
        return "outside", "general advice, not a control"
    if re.search(r"(?i)\b(?:choose|select|pick|use)\s+(?:an?|the)\s+[\w\s,-]{1,40}\b(?:that is|that's)\s+not\b", t):
        return "outside", "general advice, not a control"
    if re.search(r"(?i)\bkeep the\b.*?\bdialog box open and go to the next\b", t):
        return "outside", "transitional instruction between procedures"
    if re.search(r"(?i)\bthen you assign an action that will occur\b", t):
        return "outside", "explanatory sentence, not an action"
    m = LAUNCH_RX.match(t)
    if m:
        name = m.group(1).lower().strip()
        ui_thing = re.search(r"\b(tab|menu|dialog|dialog box|pane|panel|window|box|list|toolbar|ribbon|settings|options|preferences|file|folder|document|presentation|workbook|image|picture|page|view|tool)s?$", name)
        if not ui_thing and (any(w in name.split() or w == name.replace(" ", "") for w in app_words) or re.fullmatch(r"(?:the )?(?:app|application|program)", name)):
            return "launch", "starts the application (done by the launcher)"
    if SCENARIO_RX.search(t):
        return "outside", "reading guidance (which section of the article applies), not an action on the application"
    if OBJECT_REF_RX.search(t):
        return "content", "acts on an object in the document (" + OBJECT_REF_RX.search(t).group(1).strip() + "): the run selects one it created"
    if DIALOG_BUTTON_RX.match(t):
        return "dialog", "a standard dialog button: found in the dialog that is open at that moment"
    if CONTENT_RX.search(t) and not re.search(r"\*\*", raw or "") and not CONTROL_NOUN_RX.search(t):        # 'click the Text button' names a control, not the text
        return "content", "acts on the document's own content (selection / insertion point / typed text)"
    return "ui", ""



# ------------------------------------------------------------------------------------------------------------- page quality
def procedural_quality(text: str) -> Dict[str, Any]:
    """Share of the page's lines that read as procedure (numbered / bulleted imperative lines, interface terms in bold, menu paths). Low = marketing, news, a link farm."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return {"score": 0.0, "why": "no text"}
    proc = sum(1 for ln in lines if re.match(r"(?i)^(?:\d+[.)]|[-*•])?\s*(?:click|select|choose|press|open|go to|type|enter|tap|drag|right-click|double-click|check|clear|turn|switch|on the|in the|under)\b", ln)
               or "**" in ln or re.search(r"\w\s*>\s*\w", ln))
    noise = sum(1 for ln in lines if NOISE_RX.search(ln))
    score = max(0.0, (proc - 2 * noise) / len(lines))
    return {"score": round(score, 3), "why": f"{proc} procedural line(s) of {len(lines)}" + (f", {noise} boiler-plate" if noise else "")}
