import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import 'apple_design.dart';
import 'board_api.dart';

enum PreviewDevice { desktop, tablet, mobile }

extension PreviewDeviceInfo on PreviewDevice {
  String get label => switch (this) {
    PreviewDevice.desktop => 'Desktop',
    PreviewDevice.tablet => 'Tablet',
    PreviewDevice.mobile => 'Mobile',
  };

  double? get maxWidth => switch (this) {
    PreviewDevice.desktop => null,
    PreviewDevice.tablet => 768,
    PreviewDevice.mobile => 390,
  };
}

/// Builds the URL of a rendered workspace page, reusing
/// `GET /site-manager/preview/<path>`.
Uri previewFileUri(Uri base, String path) {
  final clean = path.trim().replaceAll(RegExp(r'^/+'), '');
  final target = clean.isEmpty ? 'index.html' : clean;
  final encoded = target.split('/').map(Uri.encodeComponent).join('/');
  return base.resolve('/site-manager/preview/$encoded');
}

/// Only workspace preview pages can send selections to the native editor.
String? previewPathFromUri(Uri base, String url) {
  final uri = Uri.tryParse(url);
  const prefix = '/site-manager/preview/';
  if (uri == null ||
      !uri.hasAuthority ||
      !{'http', 'https'}.contains(uri.scheme) ||
      uri.origin != base.origin ||
      !uri.path.startsWith(prefix)) {
    return null;
  }
  final path = Uri.decodeComponent(uri.path.substring(prefix.length));
  return path.isEmpty ? 'index.html' : path;
}

/// Payload for `POST /api/site-manager/preview/select`, mirroring the web
/// Studio flow (selection plus the active workspace path).
Map<String, dynamic> previewSelectionPayload(
  Map<String, dynamic> selection,
  String workspacePath,
) => {
  ...selection,
  if (workspacePath.isNotEmpty) 'expected_directory_path': workspacePath,
};

String selectionLabel(Map<String, dynamic> selection) {
  final selector = selection['selector']?.toString() ?? 'element';
  final text = selection['text']?.toString() ?? '';
  return text.isEmpty ? selector : '$selector — ${text.truncate(80)}';
}

extension on String {
  String truncate(int max) => length <= max ? this : substring(0, max);
}

/// Visual picker shim injected into the top-level preview web view.
///
/// The shipped `preview-picker.js` only runs inside an iframe
/// (`window.top !== window.self`), so a native top-level view injects this
/// equivalent. It captures the same payload
/// (`page, selector, tag, text, html, image_src`) consumed by
/// `POST /api/site-manager/preview/select`.
const _pickerShim = r'''
(() => {
  if (window.__oneboardPickerInstalled) return;
  window.__oneboardPickerInstalled = true;
  let active = false;
  let hovered = null;
  const style = document.createElement('style');
  style.textContent =
    '.oneboard-pick-hover{outline:2px solid #0d6efd !important;outline-offset:2px;cursor:crosshair !important}' +
    '.oneboard-picking,.oneboard-picking *{cursor:crosshair !important}';
  (document.head || document.documentElement).appendChild(style);
  function selectorFor(element) {
    if (element.id) return '#' + CSS.escape(element.id);
    if (element === document.documentElement) return 'html';
    const parts = [];
    let node = element;
    while (node && node.nodeType === 1 && node !== document.body && parts.length < 8) {
      let name = node.tagName.toLowerCase();
      const parent = node.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter(
          (child) => child.tagName === node.tagName
        );
        if (siblings.length > 1) {
          name += ':nth-of-type(' + (siblings.indexOf(node) + 1) + ')';
        }
      }
      parts.unshift(name);
      node = parent;
    }
    parts.unshift('body');
    return parts.join(' > ');
  }
  function visibleText(element) {
    const text = (element.innerText || element.textContent || '').replace(/\s+/g, ' ').trim();
    return text.slice(0, 500);
  }
  window.__oneboardSetPicking = function (value) {
    active = !!value;
    document.documentElement.classList.toggle('oneboard-picking', active);
    if (!active && hovered) {
      hovered.classList.remove('oneboard-pick-hover');
      hovered = null;
    }
  };
  document.addEventListener('mouseover', (event) => {
    if (!active) return;
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (hovered && hovered !== target) hovered.classList.remove('oneboard-pick-hover');
    hovered = target;
    hovered.classList.add('oneboard-pick-hover');
  }, true);
  document.addEventListener('mouseout', (event) => {
    if (!active) return;
    const target = event.target;
    if (target instanceof Element) target.classList.remove('oneboard-pick-hover');
    if (hovered === target) hovered = null;
  }, true);
  document.addEventListener('click', (event) => {
    if (!active) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const target = event.target;
    if (!(target instanceof Element)) return;
    const selection = {
      page: window.__oneboardPage || '',
      selector: selectorFor(target),
      tag: target.tagName.toLowerCase(),
      text: visibleText(target),
      html: target.outerHTML.slice(0, 2000),
      image_src: target.tagName === 'IMG' ? (target.getAttribute('src') || '').slice(0, 500) : ''
    };
    OneboardSelection.postMessage(JSON.stringify(selection));
    window.__oneboardSetPicking(false);
  }, true);
})();
''';

/// Real visual preview of the connected site: rendered page, element picker,
/// assistant apply, device sizes, and before/after update comparison.
class PreviewPanel extends StatefulWidget {
  const PreviewPanel({
    super.key,
    required this.api,
    required this.workspacePath,
    this.initialPath = 'index.html',
    this.initialUpdateId,
    this.onAssistantResult,
  });

  final BoardApi api;
  final String workspacePath;
  final String initialPath;
  final int? initialUpdateId;
  final void Function(Map<String, dynamic> result)? onAssistantResult;

  @override
  State<PreviewPanel> createState() => _PreviewPanelState();
}

class _PreviewPanelState extends State<PreviewPanel> {
  late final TextEditingController _pathController;
  late final TextEditingController _promptController;
  late Future<void> _ready;
  WebViewController? _controller;
  PreviewDevice _device = PreviewDevice.desktop;
  bool _loadingPage = true;
  bool _selecting = false;
  bool _busy = false;
  String? _error;
  String? _loadedPath;
  String _workspacePath = '';
  Map<String, dynamic>? _selection;
  List<Map<String, dynamic>> _updates = [];
  int? _selectedUpdateId;
  Map<String, dynamic>? _compare;

  @override
  void initState() {
    super.initState();
    _pathController = TextEditingController(text: widget.initialPath);
    _promptController = TextEditingController();
    _selectedUpdateId = widget.initialUpdateId;
    _workspacePath = widget.workspacePath;
    _ready = _init();
  }

  @override
  void dispose() {
    _pathController.dispose();
    _promptController.dispose();
    super.dispose();
  }

  Future<void> _init() async {
    final cookies = WebViewCookieManager();
    for (final entry in widget.api.sessionCookies.entries) {
      await cookies.setCookie(
        WebViewCookie(
          name: entry.key,
          value: entry.value,
          domain: widget.api.base.host,
        ),
      );
    }
    if (!mounted) return;
    final controller = WebViewController();
    _controller = controller;
    // WebKit's opaque/background-color bridge is iOS-only. The default
    // WKWebView background already matches the white preview surface on macOS.
    await controller.setJavaScriptMode(JavaScriptMode.unrestricted);
    await controller.addJavaScriptChannel(
      'OneboardSelection',
      onMessageReceived: _onSelectionMessage,
    );
    await controller.setNavigationDelegate(
      NavigationDelegate(
        onNavigationRequest: (request) {
          if (!request.isMainFrame ||
              previewPathFromUri(widget.api.base, request.url) != null) {
            return NavigationDecision.navigate;
          }
          if (mounted) {
            setState(() {
              _loadingPage = false;
              _error =
                  'Open a page from the connected site to edit it. External navigation is unavailable in the editor.';
            });
          }
          return NavigationDecision.prevent;
        },
        onPageStarted: (_) {
          if (!mounted) return;
          setState(() {
            _loadingPage = true;
            _loadedPath = null;
            _selection = null;
            _selecting = false;
          });
        },
        onPageFinished: (url) async {
          final path = previewPathFromUri(widget.api.base, url);
          if (!mounted || path == null) return;
          try {
            await controller.runJavaScript(_pickerShim);
            await controller.runJavaScript(
              'window.__oneboardPage = ${jsonEncode(path)};',
            );
            if (!mounted) return;
            setState(() {
              _loadedPath = path;
              _pathController.text = path;
              _loadingPage = false;
            });
          } catch (error) {
            if (mounted) {
              setState(() {
                _loadingPage = false;
                _error = 'Could not initialize element selection: $error';
              });
            }
          }
        },
        onHttpError: (error) {
          if (!mounted) return;
          final failed = error.request?.uri;
          if (failed != null &&
              failed.path !=
                  previewFileUri(widget.api.base, _pathController.text).path) {
            return;
          }
          setState(() {
            _loadingPage = false;
            _error =
                'Preview returned HTTP ${error.response?.statusCode}. Check your session, project and page path.';
          });
        },
        onWebResourceError: (error) {
          if (error.isForMainFrame == true && mounted) {
            setState(() {
              _loadingPage = false;
              _error = 'Could not load the page: ${error.description}';
            });
          }
        },
      ),
    );
    await _loadUpdates();
    if (_selectedUpdateId != null) await _loadCompare(_selectedUpdateId!);
    await _openPath(_pathController.text);
  }

  Future<void> _loadUpdates() async {
    try {
      final response = await widget.api.get('/api/site-manager');
      final manager =
          (response['manager'] as Map?)?.cast<String, dynamic>() ?? {};
      final updates = (manager['updates'] as List?) ?? [];
      _workspacePath =
          (manager['directory'] as Map?)?['path']?.toString() ??
          widget.workspacePath;
      if (!mounted) return;
      setState(() {
        _updates = updates
            .whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList();
      });
    } catch (_) {
      // Updates power the compare picker only; the visual preview works
      // without them.
    }
  }

  Future<void> _openPath(String path) async {
    if (!mounted) return;
    setState(() {
      _loadingPage = true;
      _error = null;
      _selection = null;
      _selecting = false;
      _loadedPath = null;
    });
    try {
      await _controller?.loadRequest(previewFileUri(widget.api.base, path));
    } catch (error) {
      if (mounted) {
        setState(() {
          _loadingPage = false;
          _error = 'Could not open preview: $error';
        });
      }
    }
  }

  Future<void> _toggleSelecting() async {
    if (_loadingPage || _loadedPath == null) return;
    final selecting = !_selecting;
    try {
      await _controller?.runJavaScript(
        'window.__oneboardSetPicking($selecting);',
      );
      if (mounted) {
        setState(() {
          _selecting = selecting;
          _error = null;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() => _error = 'Could not select an element: $error');
      }
    }
  }

  Future<void> _onSelectionMessage(JavaScriptMessage message) async {
    Map<String, dynamic> selection;
    try {
      selection = (jsonDecode(message.message) as Map).cast<String, dynamic>();
    } catch (_) {
      return;
    }
    if (!mounted ||
        _busy ||
        _loadedPath == null ||
        selection['page'] != _loadedPath) {
      return;
    }
    setState(() {
      _busy = true;
      _selecting = false;
      _error = null;
    });
    try {
      final response = await widget.api.post(
        '/api/site-manager/preview/select',
        previewSelectionPayload(selection, _workspacePath),
      );
      if (!mounted) return;
      setState(() {
        _selection =
            (response['selection'] as Map?)?.cast<String, dynamic>() ??
            selection;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _clearSelection() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.api.call('DELETE', '/api/site-manager/preview/select');
    } catch (_) {
      // Clearing is best-effort, mirroring the web Studio behavior.
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _selection = null;
          _promptController.clear();
        });
      }
    }
  }

  Future<void> _applyAssistant() async {
    final prompt = _promptController.text.trim();
    if (prompt.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      // Restore this view's selection immediately before the AI request;
      // another preview/tab may have changed the server-side selection.
      if (_selection != null) {
        await widget.api.post(
          '/api/site-manager/preview/select',
          previewSelectionPayload(_selection!, _workspacePath),
        );
      } else {
        await widget.api.call('DELETE', '/api/site-manager/preview/select');
      }
      final payload = <String, dynamic>{'prompt': prompt};
      if (_workspacePath.isNotEmpty) {
        payload['expected_directory_path'] = _workspacePath;
      }
      final result = await widget.api.post(
        '/api/site-manager/codex-update',
        payload,
      );
      if (!mounted) return;
      final terminal = result['terminal'];
      if (terminal is Map &&
          terminal['exit_code'] != null &&
          terminal['exit_code'] != 0) {
        throw Exception(
          terminal['output'] ?? 'The AI could not apply this change.',
        );
      }
      _promptController.clear();
      await _loadUpdates();
      await _controller?.clearCache();
      await _openPath(_pathController.text);
      if (mounted) widget.onAssistantResult?.call(result);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _loadCompare(int updateId) async {
    setState(() {
      _busy = true;
      _error = null;
      _compare = null;
    });
    try {
      final compare = await widget.api.get(
        '/api/site-manager/updates/$updateId/compare',
      );
      if (!mounted) return;
      setState(() => _compare = compare);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<void>(
      future: _ready,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const BoardSurface(
            child: Padding(
              padding: EdgeInsets.all(48),
              child: Center(child: CircularProgressIndicator()),
            ),
          );
        }
        if (snapshot.hasError) {
          return BoardSurface(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Preview could not start.',
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: boardInk,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '${snapshot.error}'.replaceFirst('Exception: ', ''),
                  style: const TextStyle(color: boardMuted, fontSize: 13),
                ),
                const SizedBox(height: 14),
                OutlinedButton.icon(
                  onPressed: () => setState(() => _ready = _init()),
                  icon: const Icon(Icons.refresh_rounded, size: 16),
                  label: const Text('Retry'),
                ),
              ],
            ),
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            BoardSurface(child: _previewCard()),
            const SizedBox(height: 16),
            BoardSurface(child: _compareCard()),
          ],
        );
      },
    );
  }

  Widget _previewCard() => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Row(
        children: [
          const Expanded(
            child: Text(
              'Visual Preview',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: boardInk,
              ),
            ),
          ),
          SegmentedButton<PreviewDevice>(
            segments: PreviewDevice.values
                .map(
                  (device) =>
                      ButtonSegment(value: device, label: Text(device.label)),
                )
                .toList(),
            selected: {_device},
            onSelectionChanged: (selected) =>
                setState(() => _device = selected.first),
          ),
        ],
      ),
      const SizedBox(height: 6),
      const Text(
        'See the connected site exactly as visitors see it.',
        style: TextStyle(color: boardMuted, fontSize: 13),
      ),
      const SizedBox(height: 14),
      Row(
        children: [
          Expanded(
            child: TextField(
              controller: _pathController,
              onSubmitted: (_) => _openPath(_pathController.text),
              decoration: const InputDecoration(
                labelText: 'Page',
                hintText: 'index.html',
                prefixIcon: Icon(Icons.language_outlined),
              ),
            ),
          ),
          const SizedBox(width: 10),
          OutlinedButton.icon(
            onPressed: _busy ? null : () => _openPath(_pathController.text),
            icon: const Icon(Icons.open_in_browser_rounded, size: 16),
            label: const Text('Open'),
          ),
          const SizedBox(width: 8),
          FilledButton.icon(
            onPressed: _busy || _loadingPage || _loadedPath == null
                ? null
                : _toggleSelecting,
            icon: Icon(
              _selecting ? Icons.ads_click_rounded : Icons.ads_click_outlined,
              size: 16,
            ),
            label: Text(_selecting ? 'Selecting…' : 'Select element'),
          ),
        ],
      ),
      if (_error != null) ...[
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(11),
          decoration: BoxDecoration(
            color: const Color(0xFFB33142).withValues(alpha: .08),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text(
            _error!,
            style: const TextStyle(color: Color(0xFFB33142), fontSize: 12),
          ),
        ),
      ],
      const SizedBox(height: 12),
      Container(
        decoration: BoxDecoration(
          border: Border.all(color: const Color(0xFFE5E5EA)),
          borderRadius: BorderRadius.circular(12),
        ),
        clipBehavior: Clip.antiAlias,
        child: SizedBox(
          height: 480,
          child: Stack(
            children: [
              Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    maxWidth: _device.maxWidth ?? double.infinity,
                  ),
                  child: _controller == null
                      ? const SizedBox.shrink()
                      : WebViewWidget(controller: _controller!),
                ),
              ),
              if (_loadingPage)
                const Center(child: CircularProgressIndicator()),
            ],
          ),
        ),
      ),
      if (_selection != null) ...[
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: boardBlue.withValues(alpha: .07),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Selected element',
                style: TextStyle(color: boardMuted, fontSize: 12),
              ),
              const SizedBox(height: 4),
              SelectableText(
                selectionLabel(_selection!),
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: boardInk,
                ),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _promptController,
                      onSubmitted: (_) => _applyAssistant(),
                      decoration: const InputDecoration(
                        labelText: 'Describe the change',
                        hintText: 'Make this heading larger and centered',
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: _busy ? null : _applyAssistant,
                    child: const Text('Apply'),
                  ),
                  TextButton(
                    onPressed: _busy ? null : _clearSelection,
                    child: const Text('Clear'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    ],
  );

  Widget _compareCard() {
    final updateIds = <int, String>{};
    for (final update in _updates) {
      final id = int.tryParse('${update['id']}');
      if (id == null) continue;
      final summary = update['summary']?.toString() ?? '';
      final status = update['status']?.toString() ?? '';
      updateIds[id] = '#$id · ${summary.isEmpty ? status : summary}'
          .trim()
          .replaceAll(RegExp(r'\s+'), ' ');
    }
    final selectedValid =
        _selectedUpdateId != null && updateIds.containsKey(_selectedUpdateId);
    final files = (_compare?['files'] as List?) ?? [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Before / after',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            color: boardInk,
          ),
        ),
        const SizedBox(height: 6),
        const Text(
          'Compare what an assistant update changed.',
          style: TextStyle(color: boardMuted, fontSize: 13),
        ),
        const SizedBox(height: 12),
        if (updateIds.isEmpty)
          const Text(
            'No updates yet. Run the site assistant from Studio first.',
            style: TextStyle(color: boardMuted, fontSize: 13),
          )
        else
          Row(
            children: [
              Expanded(
                child: DropdownButtonFormField<int>(
                  initialValue: selectedValid ? _selectedUpdateId : null,
                  hint: const Text('Choose an update'),
                  items: updateIds.entries
                      .map(
                        (entry) => DropdownMenuItem(
                          value: entry.key,
                          child: Text(
                            entry.value,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      )
                      .toList(),
                  onChanged: (value) => setState(() {
                    _selectedUpdateId = value;
                    _compare = null;
                  }),
                  decoration: const InputDecoration(labelText: 'Update'),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(
                onPressed: !selectedValid || _busy
                    ? null
                    : () => _loadCompare(_selectedUpdateId!),
                child: const Text('Compare'),
              ),
            ],
          ),
        for (final file in files.whereType<Map>())
          CompareFileCard(api: widget.api, file: file.cast<String, dynamic>()),
      ],
    );
  }
}

/// One file of an update comparison, mirroring `update_compare.html`:
/// side-by-side views for visual files, fetched text for text files.
class CompareFileCard extends StatelessWidget {
  const CompareFileCard({super.key, required this.api, required this.file});

  final BoardApi api;
  final Map<String, dynamic> file;

  @override
  Widget build(BuildContext context) {
    final path = file['path']?.toString() ?? 'file';
    final change = file['change']?.toString() ?? 'modified';
    final kind = file['kind']?.toString() ?? 'binary';
    final beforeUrl = file['before_url']?.toString();
    final afterUrl = file['after_url']?.toString();
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Container(
        decoration: BoxDecoration(
          border: Border.all(color: const Color(0xFFE5E5EA)),
          borderRadius: BorderRadius.circular(12),
        ),
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    path,
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: boardInk,
                    ),
                  ),
                ),
                _chip(change),
                const SizedBox(width: 6),
                _chip(kind),
              ],
            ),
            const SizedBox(height: 8),
            if (kind == 'visual')
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: _labeledPane('Before', beforeUrl, added: true),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _labeledPane('After', afterUrl, added: false),
                  ),
                ],
              )
            else if (kind == 'text')
              _CompareText(api: api, beforeUrl: beforeUrl, afterUrl: afterUrl)
            else
              Text(
                change == 'created'
                    ? 'This file was added.'
                    : change == 'deleted'
                    ? 'This file was removed.'
                    : 'This binary file changed.',
                style: const TextStyle(color: boardMuted, fontSize: 13),
              ),
          ],
        ),
      ),
    );
  }

  Widget _chip(String label) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
    decoration: BoxDecoration(
      color: const Color(0xFFF2F2F7),
      borderRadius: BorderRadius.circular(20),
    ),
    child: Text(label, style: const TextStyle(fontSize: 11, color: boardMuted)),
  );

  Widget _labeledPane(String label, String? url, {required bool added}) =>
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontSize: 12, color: boardMuted)),
          const SizedBox(height: 4),
          SizedBox(
            height: 260,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: url == null
                  ? Container(
                      color: const Color(0xFFF2F2F7),
                      alignment: Alignment.center,
                      child: Text(
                        added
                            ? 'Added in this update'
                            : 'Removed in this update',
                        style: const TextStyle(color: boardMuted, fontSize: 12),
                      ),
                    )
                  : _CompareWebView(api: api, url: url),
            ),
          ),
        ],
      );
}

class _CompareWebView extends StatefulWidget {
  const _CompareWebView({required this.api, required this.url});

  final BoardApi api;
  final String url;

  @override
  State<_CompareWebView> createState() => _CompareWebViewState();
}

class _CompareWebViewState extends State<_CompareWebView> {
  late final WebViewController _controller;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..loadRequest(widget.api.base.resolve(widget.url));
  }

  @override
  Widget build(BuildContext context) => WebViewWidget(controller: _controller);
}

class _CompareText extends StatefulWidget {
  const _CompareText({
    required this.api,
    required this.beforeUrl,
    required this.afterUrl,
  });

  final BoardApi api;
  final String? beforeUrl;
  final String? afterUrl;

  @override
  State<_CompareText> createState() => _CompareTextState();
}

class _CompareTextState extends State<_CompareText> {
  late final Future<(String?, String?)> _texts;

  @override
  void initState() {
    super.initState();
    _texts = _load();
  }

  Future<String?> _fetch(String? url) async {
    if (url == null) return null;
    final bytes = await widget.api.getBytes(url);
    return utf8.decode(bytes, allowMalformed: true);
  }

  Future<(String?, String?)> _load() async =>
      (await _fetch(widget.beforeUrl), await _fetch(widget.afterUrl));

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<(String?, String?)>(
      future: _texts,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Padding(
            padding: EdgeInsets.all(20),
            child: Center(child: CircularProgressIndicator()),
          );
        }
        if (snapshot.hasError) {
          return Text(
            'Could not load file contents: ${snapshot.error}'.replaceFirst(
              'Exception: ',
              '',
            ),
            style: const TextStyle(color: boardMuted, fontSize: 12),
          );
        }
        final texts = snapshot.data ?? (null, null);
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(child: _pane('Before', texts.$1, added: true)),
            const SizedBox(width: 8),
            Expanded(child: _pane('After', texts.$2, added: false)),
          ],
        );
      },
    );
  }

  Widget _pane(String label, String? text, {required bool added}) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(label, style: const TextStyle(fontSize: 12, color: boardMuted)),
      const SizedBox(height: 4),
      Container(
        constraints: const BoxConstraints(maxHeight: 260),
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: const Color(0xFFF9F9FB),
          borderRadius: BorderRadius.circular(8),
        ),
        child: SingleChildScrollView(
          child: SelectableText(
            text ??
                (added ? 'Added in this update.' : 'Removed in this update.'),
            style: const TextStyle(
              fontSize: 12,
              height: 1.55,
              fontFamily: 'Menlo',
              fontFamilyFallback: ['monospace'],
            ),
          ),
        ),
      ),
    ],
  );
}
