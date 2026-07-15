ObjC.import("CoreGraphics");
ObjC.import("Foundation");

function safeRead(element, propertyName, fallback) {
  try {
    var value = element[propertyName]();
    if (value === undefined || value === null) return fallback;
    return value;
  } catch (_error) {
    return fallback;
  }
}

function textValue(value, limit) {
  if (value === undefined || value === null) return "";
  var text;
  try {
    text = String(value);
  } catch (_error) {
    return "";
  }
  return text.length > limit ? text.slice(0, limit) : text;
}

function pairValue(value) {
  if (!value || value.length < 2) return null;
  return [Number(value[0]), Number(value[1])];
}

function findProcess(systemEvents, names) {
  var processes = systemEvents.processes();
  for (var n = 0; n < names.length; n += 1) {
    for (var p = 0; p < processes.length; p += 1) {
      if (textValue(safeRead(processes[p], "name", ""), 200) === names[n]) {
        return processes[p];
      }
    }
  }
  throw new Error("app process not found");
}

function actionNames(element) {
  try {
    return element.actions().map(function (action) {
      return textValue(safeRead(action, "name", ""), 100);
    }).filter(function (name) { return name.length > 0; });
  } catch (_error) {
    return [];
  }
}

function elementRecord(element, elementId, depth, includeValues) {
  var position = pairValue(safeRead(element, "position", null));
  var size = pairValue(safeRead(element, "size", null));
  var role = textValue(safeRead(element, "role", ""), 200);
  var subrole = textValue(safeRead(element, "subrole", ""), 200);
  var bounds = null;
  if (position && size) {
    bounds = {x: position[0], y: position[1], width: size[0], height: size[1]};
  }
  var record = {
    element_id: elementId,
    depth: depth,
    role: role,
    subrole: subrole,
    title: textValue(safeRead(element, "title", ""), 500),
    description: textValue(safeRead(element, "description", ""), 500),
    identifier: textValue(safeRead(element, "accessibilityIdentifier", ""), 500),
    enabled: safeRead(element, "enabled", null),
    focused: safeRead(element, "focused", null),
    selected: safeRead(element, "selected", null),
    actions: actionNames(element),
    bounds: bounds
  };
  if (includeValues) {
    if (role === "AXSecureTextField" || subrole === "AXSecureTextField") {
      record.value_redacted = true;
    } else {
      record.value = textValue(safeRead(element, "value", ""), 1000);
    }
  }
  return record;
}

function collectTree(root, maxDepth, maxElements, includeValues) {
  var elements = [];
  var truncated = false;

  function walk(parent, path, depth) {
    if (depth > maxDepth || truncated) return;
    var children;
    try {
      children = parent.uiElements();
    } catch (_error) {
      return;
    }
    for (var i = 0; i < children.length; i += 1) {
      if (elements.length >= maxElements) {
        truncated = true;
        return;
      }
      var childPath = path.concat([i + 1]);
      elements.push(elementRecord(children[i], "ax:" + childPath.join("."), depth, includeValues));
      walk(children[i], childPath, depth + 1);
      if (truncated) return;
    }
  }

  walk(root, [], 1);
  return {elements: elements, truncated: truncated};
}

function tree(input) {
  var systemEvents = Application("System Events");
  var process = findProcess(systemEvents, input.process_names);
  var windows = process.windows();
  if (windows.length < input.window_index) throw new Error("window not found");
  var window = windows[input.window_index - 1];
  var collected = collectTree(window, input.max_depth, input.max_elements, input.include_values);
  return {
    process_name: textValue(safeRead(process, "name", ""), 200),
    window: {
      title: textValue(safeRead(window, "title", ""), 500),
      role: textValue(safeRead(window, "role", ""), 200),
      subrole: textValue(safeRead(window, "subrole", ""), 200)
    },
    elements: collected.elements,
    count: collected.elements.length,
    truncated: collected.truncated
  };
}

function resolveElement(window, elementId) {
  if (elementId === "ax:root") return window;
  if (!/^ax:\\d+(\\.\\d+)*$/.test(elementId)) throw new Error("invalid element_id");
  var indices = elementId.slice(3).split(".").map(function (part) { return Number(part); });
  var current = window;
  for (var i = 0; i < indices.length; i += 1) {
    var children = current.uiElements();
    var index = indices[i] - 1;
    if (index < 0 || index >= children.length) throw new Error("accessibility element not found");
    current = children[index];
  }
  return current;
}

function performNamedAction(element, name) {
  var actions = element.actions();
  for (var i = 0; i < actions.length; i += 1) {
    if (textValue(safeRead(actions[i], "name", ""), 100) === name) {
      actions[i].perform();
      return true;
    }
  }
  return false;
}

function elementCenter(element) {
  var position = pairValue(safeRead(element, "position", null));
  var size = pairValue(safeRead(element, "size", null));
  if (!position || !size || size[0] <= 0 || size[1] <= 0) throw new Error("element has no usable bounds");
  return {x: position[0] + size[0] / 2, y: position[1] + size[1] / 2};
}

function postMouseEvent(eventType, point) {
  var event = $.CGEventCreateMouseEvent(null, eventType, point, $.kCGMouseButtonLeft);
  if (!event) throw new Error("unable to create mouse event");
  $.CGEventPost($.kCGHIDEventTap, event);
}

function dragElements(source, target) {
  var start = elementCenter(source);
  var end = elementCenter(target);
  var currentApp = Application.currentApplication();
  postMouseEvent($.kCGEventMouseMoved, start);
  postMouseEvent($.kCGEventLeftMouseDown, start);
  for (var step = 1; step <= 12; step += 1) {
    var ratio = step / 12;
    postMouseEvent($.kCGEventLeftMouseDragged, {
      x: start.x + (end.x - start.x) * ratio,
      y: start.y + (end.y - start.y) * ratio
    });
    currentApp.delay(0.015);
  }
  postMouseEvent($.kCGEventLeftMouseUp, end);
}

function accessibilityAction(input) {
  var systemEvents = Application("System Events");
  var process = findProcess(systemEvents, input.process_names);
  var windows = process.windows();
  if (windows.length < input.window_index) throw new Error("window not found");
  var window = windows[input.window_index - 1];
  var element = resolveElement(window, input.element_id || "ax:root");
  var performed = false;

  if (input.action === "click" || input.action === "menu_select") {
    performed = performNamedAction(element, "AXPress");
    if (!performed) {
      try {
        element.click();
        performed = true;
      } catch (_error) {
        throw new Error("element does not support click");
      }
    }
  } else if (input.action === "input") {
    try {
      element.focused = true;
      element.value = input.text;
      performed = true;
    } catch (_error) {
      throw new Error("element does not support text input");
    }
  } else if (input.action === "scroll") {
    var directionName = input.direction.charAt(0).toUpperCase() + input.direction.slice(1);
    var actionCandidates = ["AXScroll" + directionName, "AXScrollPage" + directionName];
    for (var scrollIndex = 0; scrollIndex < input.amount; scrollIndex += 1) {
      var scrolled = false;
      for (var candidateIndex = 0; candidateIndex < actionCandidates.length; candidateIndex += 1) {
        if (performNamedAction(element, actionCandidates[candidateIndex])) {
          scrolled = true;
          break;
        }
      }
      if (!scrolled) throw new Error("element does not support semantic scroll");
    }
    performed = true;
  } else if (input.action === "drag") {
    var target = resolveElement(window, input.target_element_id);
    dragElements(element, target);
    performed = true;
  } else if (input.action === "file_dialog_choose") {
    process.frontmost = true;
    systemEvents.keystroke("g", {using: ["command down", "shift down"]});
    Application.currentApplication().delay(0.2);
    systemEvents.keystroke(input.path);
    systemEvents.keyCode(36);
    Application.currentApplication().delay(0.3);
    systemEvents.keyCode(36);
    performed = true;
  } else {
    throw new Error("unsupported accessibility action");
  }

  return {
    command: input.action,
    element_id: input.element_id || "ax:root",
    performed: performed,
    role: textValue(safeRead(element, "role", ""), 200),
    title: textValue(safeRead(element, "title", ""), 500)
  };
}

function run(argv) {
  if (argv.length < 1) throw new Error("missing JSON request");
  var input = JSON.parse(argv[0]);
  if (input.command === "tree") return JSON.stringify(tree(input));
  if (input.command === "action") return JSON.stringify(accessibilityAction(input));
  throw new Error("unsupported accessibility command");
}
