import subprocess
import argparse
import re
from typing import List

RE_GROUPS = re.compile(r"^\[(?P<group>.*?)\](?P<content>.*)$")
RE_GIT_COMMIT_AUTHOR = re.compile(r"^Author:.*<(?P<author>[a-zA-Z\-]+)@.*>$")
RE_GIT_COMMIT_CHERRYPICK = re.compile(
    r"^\(cherry picked from commit (?P<commit>[0-9a-f]+)\)$"
)
RE_GIT_COMMIT_PIPER_TAG = re.compile(r" +PiperOrigin-RevId: (?P<cl>[0-9]+)$")
RE_GIT_MERGE = re.compile(r"^Merged.*")
RE_OPTIONS = re.compile(
    r"(\s.*Options[\s,\.!?\\-_]?)|(.*Option (in)?to *Calculator[\s,\.!?\\-_]?)",
    re.IGNORECASE,
)
RE_CALCULATOR = re.compile(r"\s.*Calculator[\s,\.!?\\-_]?")
RE_SUPPORT_FOR = re.compile(r"support( for)?", re.IGNORECASE)
RE_ANDROID_CHANGES = re.compile(
    r"(\saar[\s,\.!?\\-_]?)|(java[\s,\.!?\\-_]?)|(android)", re.IGNORECASE
)
RE_BUG_FIX = re.compile(r"\sfix(ed)?", re.IGNORECASE)
RE_DEPS = re.compile(r"dependenc(ies|y)[\s,\.!?\\-_]?", re.IGNORECASE)
RE_IOS = re.compile(r"\sios[\s,\.!?\\-_]?", re.IGNORECASE)
RE_BAZEL = re.compile(r"bazel", re.IGNORECASE)


def check_fine_grained_framework_items(message: str) -> bool:
    """
    Checks if the given string contains any hint that the change is done in Calculators, 
    Calculator Options, Proto options or new support added.
    Return True if any of the above conditions are met; else False.

    Parameters
    ----------
    message: str
      The commit title to infer the change from

    Returns
    -------
    bool
      Indication of whether it is a framework change or not
    """
    if (
        re.search(RE_OPTIONS, message)
        or re.search(RE_CALCULATOR, message)
        or re.search(RE_SUPPORT_FOR, message)
    ):
        return True

    return False


def sentence(text: str) -> str:
    """
    Convert the first letter in a given string to uppercase

    Parameters
    ----------
    text: str
      The text to capitalize the first letter of

    Returns
    -------
    str
      A string with first letter in uppercase
    """
    text = text.strip().strip(".")
    text = text[0].upper() + text[1:]
    return text


def get_git_commits_between_commits(
    previous_commit: str, current_commit: str
) -> List[str]:
    """
    Returns list of git commits hashes between two commit hashes

    Parameters
    ----------
    previous_commit: str
      Previous Git commit hash
    current_commit: str
      Current Git commit hash

    Returns
    -------
    List[str]
      List of git commits hashes
    """
    commits = []
    # Use `git cherry` instead of `git log` to filter cherry picks correctly.
    # These appear as two different commits one on each branch.
    lines = subprocess.check_output(
        ["git", "cherry", previous_commit, current_commit], encoding="UTF-8"
    ).splitlines()
    for l in lines:
        # Only use commits on the current release branch (these are
        # prefixed with "+", see `git cherry` man page for details).
        if l.startswith("+ "):
            commits.append(l[2:])
    return commits


def parse_framework_changes(
    regex, line: str, added_options, added_calculators, added_support, framework_items
):
    if re.search(RE_OPTIONS, line):
        line = re.sub(regex, "", line)
        line = sentence(line)
        added_options.append(line)
    if re.search(RE_CALCULATOR, line):
        line = re.sub(regex, "", line)
        line = sentence(line)
        added_calculators.append(line)
    if re.search(RE_SUPPORT_FOR, line):
        line = re.sub(regex, "", line)
        line = sentence(line)
        added_support.append(line)
    else:
        line = re.sub(regex, "", line)
        line = sentence(line)
        framework_items.append(line)


class Commit:
    def __init__(self, hash: str):
        self.hash = hash
        self.message = ""
        self.commit_lines = []
        self.author = ""
        self.timestamp = None
        self.get_commit_details()
        self.parse_commit_title()
        self.parse_author()

    def get_commit_details(self):
        assert self.hash is not None

        try:
            self.commit_lines = subprocess.check_output(
                ["git", "show", "-s", "--pretty=short", self.hash], encoding="UTF-8"
            ).splitlines()
        except subprocess.CalledProcessError as error:
            print(f"{error.returncode}: {error.output}")
            return

    def parse_commit_title(self):
        # find title of the commit
        self.message = self.commit_lines[3].strip()

    def parse_author(self):
        # find author of the commit
        for l in self.commit_lines:
            m = RE_GIT_COMMIT_AUTHOR.match(l)
            if m:
                self.author = m.group("author")
                break

    def valid_release_note(self):
        assert len(self.message) > 0
        # check merge
        if re.match(RE_GIT_MERGE, self.message):
            return False
        if re.match(
            r"(Code Format(ted|ting)?)|(Updated? Format(ting)?)|formatting",
            self.message,
            re.IGNORECASE,
        ):
            return False
        if re.match(r"^Internal\s?.*\s?change", self.message, re.IGNORECASE):
            return False
        return True


def notes_from_template(
    bazel_changes: List[str],
    android_changes: List[str],
    ios_changes: List[str],
    bug_fixes: List[str],
    framework_changes: List[str],
    build_changes: List[str],
    deps_changes: List[str],
) -> str:
    android_changes = "\n".join(["- " + item for item in android_changes])
    ios_changes = "\n".join(["- " + item for item in ios_changes])
    bazel_changes = "\n".join(["- " + item for item in bazel_changes])
    bug_fixes = "\n".join(["- " + item for item in bug_fixes])
    framework_changes = "\n".join(["- " + item for item in framework_changes])
    build_changes = "\n".join(["- " + item for item in build_changes])
    deps_changes = "\n".join(["- " + item for item in deps_changes])

    x = f"""
### Build changes
{build_changes}
    
### Bazel changes
{bazel_changes}

### Framework and core calculator improvements
{framework_changes}

### MediaPipe solutions update
This section should highlight the changes that are done specifically for any platform and don't propagate to
other platforms.

#### Android
{android_changes}

#### iOS
{ios_changes}

### Bug fixes
{bug_fixes}

### MediaPipe Dependencies
{deps_changes}
  """
    if len(build_changes) == 0:
        x = x.replace("### Build changes\n", "")
    if len(bazel_changes) == 0:
        x = x.replace("### Bazel changes\n", "")
    if len(framework_changes) == 0:
        x = x.replace("### Framework and core calculator improvements\n", "")
    if len(android_changes) == 0:
        x = x.replace("#### Android\n", "")
    if len(ios_changes) == 0:
        x = x.replace("#### iOS\n", "")
    if len(bug_fixes) == 0:
        x = x.replace("### Bug fixes\n", "")
    if len(android_changes) == 0:
        x = x.replace("#### Android\n", "")
    if len(deps_changes) == 0:
        x = x.replace("### MediaPipe Dependencies\n", "")

    return x


def catalogue_rough_notes(from_commit: str, to_commit: str) -> List[str]:
    """
    Creates a rough collection of notes which is essentially a list of commit titles
    The changes like formatting, or internal changes are stripped off from this list

    Parameters
    ----------
    from_commit: str
      The commit in history to start gathering the commits from
    to_commit: str
      The commit in history to stop gathering the commits upto

    Returns
    -------
    List[str]
      A list of rough notes
    """
    notes: List[str] = []
    commit_history = get_git_commits_between_commits(from_commit, to_commit)
    commits: List[Commit] = []

    for commit_hash in commit_history:
        commit = Commit(commit_hash)
        if commit.valid_release_note():
            commits.append(commit)

    for commit in commits:
        if len(notes) > 0 and notes[-1] == commit.message:
            continue
        notes.append(commit.message)
    return notes


def section_notes(regex: str, message: str, collection: List[str]) -> bool:
    """
    Checks if the given commit message should belong to the provided list of changes
    or into the framework changes.

    Parameters
    ---------
    message: str
      The commit title

    collection: List[str]
      The list of commit messages to add the title to if not a framework change

    Returns
    -------
    bool
      A value signifying whether the commit has been added to the given list or
      to framework changes
    """
    if check_fine_grained_framework_items(message):
        parse_framework_changes(
            regex,
            message,
            added_options,
            added_calculators,
            added_support,
            framework_items,
        )
        return False
    message = sentence(message)
    collection.append(message)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from_commit",
        required=True,
        help="The commit in history to start gathering the commits from",
    )
    parser.add_argument(
        "--to_commit",
        required=True,
        help="The commit in history to stop gathering the commits upto",
    )
    parser.add_argument("--version", required=True, help="Version for the new release")
    args = parser.parse_args()

    notes = catalogue_rough_notes(args.from_commit, args.to_commit)

    framework_items = []
    added_calculators, added_support, added_options = [], [], []
    android_changes, ios_changes = [], []
    bazel_changes, bug_fixes, deps = [], [], []

    for line in notes:
        # check for Bazel changes
        if re.search(RE_BAZEL, line):
            if not section_notes(
                r"Add(ed)?", line, bazel_changes
            ) and not section_notes(r"Updated?", line, bazel_changes):
                continue

        # check for iOS changes
        if re.search(RE_IOS, line):
            if check_fine_grained_framework_items(line):
                parse_framework_changes(
                    line,
                    added_options,
                    added_calculators,
                    added_support,
                    framework_items,
                )
                continue
            if line.startswith("iOS") or line.startswith("ios"):
                ios_changes.append(line.replace("ios", "iOS"))
            else:
                line = sentence(line)
                ios_changes.append(line.replace("ios", "iOS"))

        # check for android changes
        if re.search(RE_ANDROID_CHANGES, line):
            if not section_notes(
                r"Add(ed)?", line, android_changes
            ) and not section_notes(r"Updated?", line, android_changes):
                continue

        # check for bug fixes
        if re.search(RE_BUG_FIX, line):
            if not section_notes(r"Add(ed)?", line, bug_fixes) and not section_notes(
                r"Updated?", line, bug_fixes
            ):
                continue

        # check for dependency changes
        if re.search(RE_DEPS, line):
            if not section_notes(r"Add(ed)?", line, deps) and not section_notes(
                r"Updated?", line, deps
            ):
                continue

        # check for new additions
        if re.match(r"Add(ed)?", line, re.IGNORECASE):
            parse_framework_changes(
                r"Add(ed)?",
                line,
                added_options,
                added_calculators,
                added_support,
                framework_items,
            )
            continue

        # check for new updates
        if re.match(r"Updated?", line, re.IGNORECASE):
            parse_framework_changes(
                r"Updated?",
                line,
                added_options,
                added_calculators,
                added_support,
                framework_items,
            )
            continue

    framework_changes = []
    framework_changes.append(
        f"Added {', '.join([re.sub(r'Add(ed)?', '', op, re.I) for op in added_options])}"
    )
    framework_changes.append(
        f"Added {', '.join([re.sub(r'Add(ed)?', '', cal, re.I) for cal in added_calculators])}"
    )
    framework_changes.extend(framework_items)
    framework_changes.extend(added_support)

    with open(f"release_notes_v{args.version}", "w") as file:
        file.write(
            notes_from_template(
                bazel_changes=bazel_changes,
                android_changes=android_changes,
                ios_changes=ios_changes,
                bug_fixes=bug_fixes,
                deps_changes=deps,
                framework_changes=framework_changes,
                build_changes="",
            )
        )
