import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' show CupertinoIcons;
import 'package:flutter/services.dart';

import 'package:firebase_messaging/firebase_messaging.dart';

import 'board_api.dart';
import 'security_repair.dart';
import 'auth_link_dialog.dart';
import 'calendar_panel.dart';
import 'buffer_composer.dart';
import 'feature_catalog.dart';
import 'health_panel.dart';
import 'request_thread_view.dart';
import 'settings_panel.dart';
import 'site_brand_panel.dart';
import 'teams_panel.dart';
import 'apple_design.dart';
import 'workspace_dashboard.dart';
import 'search_console_panel.dart';
import 'workspace_chrome.dart';
import 'firebase_workspace.dart';
import 'preview_panel.dart';
import 'search_palette.dart';
import 'studio_file_view.dart';
import 'studio_terminal_view.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await FirebaseWorkspace.instance.initialize();
  runApp(const OneBoardApp());
}

const navy = Color(0xFFF5F5F7);
const panel = Color(0xFFFFFFFF);
const cyan = Color(0xFF007AFF);
const _ink = Color(0xFF1D1D1F);
const _secondaryInk = Color(0xFF6E6E73);

class OneBoardApp extends StatelessWidget {
  const OneBoardApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'ONEBoard',
    debugShowCheckedModeBanner: false,
    theme: boardTheme,
    home: const OneBoardHome(),
  );
}

class OneBoardHome extends StatefulWidget {
  const OneBoardHome({super.key});

  @override
  State<OneBoardHome> createState() => _OneBoardHomeState();
}

class _OneBoardHomeState extends State<OneBoardHome> {
  static const _serviceChannel = MethodChannel('com.oneboard.flutter/service');
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _name = TextEditingController();
  final _confirmPassword = TextEditingController();
  BoardApi? _api;
  bool _busy = false;
  bool _connected = false;
  bool _authenticated = false;
  String _userName = '';
  String? _error;
  String? _authNotice;
  String _authMode = 'login';
  String _sitePath = '';
  int _section = 0;
  Map<String, dynamic> _dashboard = {};
  Map<String, dynamic> _sites = {};
  Map<String, dynamic> _featureData = {};
  Map<String, dynamic>? _featureResult;
  String _workspacePath = '';
  String? _bufferPublicImageUrl;
  bool _usingCachedData = false;
  String _previewPath = 'index.html';
  int? _previewUpdateId;

  @override
  void initState() {
    super.initState();
    FirebaseWorkspace.instance.attachForegroundMessages(
      _showPushMessage,
      onOpen: _openNotificationSection,
    );
    FirebaseWorkspace.instance.onPushToken = _registerPushDevice;
    _startService();
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _name.dispose();
    _confirmPassword.dispose();
    _api?.close();
    super.dispose();
  }

  Future<void> _action(Future<void> Function() task) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await task();
    } catch (error) {
      if (mounted) {
        setState(
          () => _error = error.toString().replaceFirst('Exception: ', ''),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  // ONEBoard for macOS is local-only: it always talks to the bundled
  // Python service on 127.0.0.1. No shared or personal server is used.
  Future<void> _startService() => _action(() async {
    final service = await _serviceChannel.invokeMapMethod<String, dynamic>(
      'startService',
    );
    final baseUrl = service?['baseUrl']?.toString();
    if (baseUrl == null || baseUrl.isEmpty) {
      throw Exception('Could not start the local service.');
    }
    BoardApi? candidate;
    try {
      candidate = BoardApi(
        baseUrl,
        serviceToken: service?['token']?.toString() ?? '',
      );
      final session = await candidate.session();
      if (session['authenticated'] is! bool) {
        throw Exception('The local service did not return a session.');
      }
      _api?.close();
      _api = candidate;
      candidate = null;
      _workspacePath = '';
      _bufferPublicImageUrl = null;
      _previewPath = 'index.html';
      _previewUpdateId = null;
      _sitePath = '';
      _sites = {};
      _dashboard = {};
      _featureData = {};
      _featureResult = null;
      _usingCachedData = false;
      _password.clear();
      _setSession(session);
    } catch (_) {
      candidate?.close();
      rethrow;
    }
  });

  Future<void> _openExternal(String url) =>
      _serviceChannel.invokeMethod<bool>('openExternalURL', url).then((_) {});

  void _setSession(Map<String, dynamic> session) {
    setState(() {
      _connected = true;
      _authenticated = session['authenticated'] == true;
      _userName = (session['user'] as Map?)?['name']?.toString() ?? '';
    });
    if (_authenticated) _loadDashboard();
  }

  Future<void> _login() => _action(() async {
    final password = _password.text;
    final response = await _api!.post('/api/auth/login', {
      'email': _email.text.trim(),
      'password': password,
    });
    await FirebaseWorkspace.instance.registerUser(
      _email.text.trim(),
      password,
      (response['user'] as Map?)?.cast<String, dynamic>() ?? {},
    );
    _setSession({'authenticated': true, 'user': response['user']});
    final pushToken = FirebaseWorkspace.instance.pushToken;
    if (pushToken != null) _registerPushDevice(pushToken);
  });

  Future<void> _register() => _action(() async {
    final response = await _api!.post('/api/auth/register', {
      'name': _name.text.trim(),
      'email': _email.text.trim(),
      'password': _password.text,
      'confirm_password': _confirmPassword.text,
    });
    setState(() {
      _authMode = 'login';
      _authNotice =
          '${response['message']?.toString() ?? 'Check your email to verify your account.'} Keep ONEBoard open while you open the verification link, then sign in here.';
    });
  });

  Future<void> _forgotPassword() => _action(() async {
    await _api!.post('/api/auth/forgot-password', {
      'email': _email.text.trim(),
    });
    setState(() {
      _authMode = 'login';
      _authNotice =
          'If the email exists, you will receive a password reset link. Keep ONEBoard open while you open it, then sign in with your new password.';
    });
  });

  Future<void> _completeEmailLink(bool reset) async {
    if (_api == null) return;
    final completed = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => AuthLinkDialog(api: _api!, reset: reset),
    );
    if (completed == true && mounted) {
      setState(() {
        _authMode = 'login';
        _password.clear();
        _authNotice = reset
            ? 'Password updated. Sign in with your new password.'
            : 'Email verified. You can now sign in.';
      });
    }
  }

  Future<void> _resendVerification() => _action(() async {
    await _api!.post('/api/auth/resend-verification', {
      'email': _email.text.trim(),
    });
    setState(
      () => _authNotice =
          'If the account is pending verification, you will receive another email.',
    );
  });

  Future<void> _loadDashboard() => _action(() async {
    try {
      _dashboard = await _api!.get('/api/dashboard');
      await FirebaseWorkspace.instance.cacheSnapshot('dashboard', _dashboard);
      _usingCachedData = false;
    } catch (error) {
      final cached = await FirebaseWorkspace.instance.readSnapshot('dashboard');
      if (cached == null) rethrow;
      _dashboard = cached;
      _usingCachedData = true;
    }
    if (mounted) setState(() => _section = 0);
  });

  Future<void> _refreshSearchConsole() async {
    final response = await _api!.get('/api/dashboard');
    if (!mounted) return;
    setState(() {
      _dashboard = response;
      _usingCachedData = false;
    });
  }

  Future<void> _connectSearchConsole() => _action(() async {
    final response = await _api!.get('/api/google-search-console/connect');
    final url = response['auth_url']?.toString();
    if (url == null || url.isEmpty) {
      throw Exception('Google authorization URL is unavailable.');
    }
    await _openExternal(url);
    if (!mounted) return;
    final completed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Connect Google Search Console'),
        content: const Text(
          'Complete Google authorization in your browser, then return here. Keep ONEBoard open during authorization.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('I’ve finished connecting'),
          ),
        ],
      ),
    );
    if (completed == true) await _refreshSearchConsole();
  });

  Future<void> _disconnectSearchConsole() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Disconnect Google?'),
        content: const Text(
          'Search performance will no longer refresh until you reconnect your account.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Disconnect'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await _action(() async {
      final response = await _api!.post(
        '/api/google-search-console/disconnect',
      );
      await _refreshSearchConsole();
      if (mounted && response['revoke_warning'] != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(response['revoke_warning'].toString())),
        );
      }
    });
  }

  Future<void> _selectSearchProperty(String property) => _action(() async {
    final scoped = (_dashboard['gsc'] as Map?)?['site_scoped'] == true;
    await _api!.post(
      scoped ? '/api/site-manager/site' : '/api/google-search-console/site',
      {
        if (scoped) 'gsc_property': property else 'site_url': property,
        if (scoped && _workspacePath.isNotEmpty)
          'expected_directory_path': _workspacePath,
      },
    );
    await _refreshSearchConsole();
  });

  Future<void> _createSearchPage(Map<String, dynamic> opportunity) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Create SEO page'),
        content: Text(
          'Create “${opportunity['title']}” in your active project using AI?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Create page'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await _action(() async {
      final result = await _api!.post('/api/seo-suggestions/create', {
        'title': opportunity['title'],
        'keyword': opportunity['keyword'],
        if (_workspacePath.isNotEmpty)
          'expected_directory_path': _workspacePath,
      });
      final sites = await _api!.get('/api/site-manager');
      if (!mounted) return;
      setState(() {
        _sites = sites;
        _featureResult = result;
        _section = 1;
      });
    });
  }

  Future<void> _loadSites() => _browseSite('');

  Future<void> _chooseSiteFolder() async {
    final path = await _serviceChannel.invokeMethod<String>('chooseDirectory');
    if (path == null || path.isEmpty || !mounted) return;
    await _action(() async {
      await _api!.post('/api/site-manager/connect', {'path': path});
      await _browseSite('');
    });
  }

  Future<void> _browseSite(
    String path, {
    bool keepResult = false,
  }) => _action(() async {
    final query = path.isEmpty ? '' : '?path=${Uri.encodeQueryComponent(path)}';
    _sites = await _api!.get('/api/site-manager$query');
    final manager = (_sites['manager'] as Map?)?.cast<String, dynamic>() ?? {};
    _workspacePath = (manager['directory'] as Map?)?['path']?.toString() ?? '';
    _sitePath = path;
    if (!keepResult) _featureResult = null;
    if (mounted) setState(() => _section = 1);
  });

  Future<void> _openPreview({String? path, int? updateId}) async {
    _previewPath = path ?? 'index.html';
    _previewUpdateId = updateId;
    await _loadFeature(2);
  }

  Future<void> _loadFeature(int index) => _action(() async {
    final page = featurePages[index - 1];
    final cacheKey = 'feature_$index';
    try {
      _featureData = await _api!.get(page.endpoint);
      await FirebaseWorkspace.instance.cacheSnapshot(cacheKey, _featureData);
      _usingCachedData = false;
    } catch (error) {
      final cached = await FirebaseWorkspace.instance.readSnapshot(cacheKey);
      if (cached == null) rethrow;
      _featureData = cached;
      _usingCachedData = true;
    }
    if (index == 13 && _featureData['notifications'] is List) {
      await FirebaseWorkspace.instance.cacheNotifications(
        _featureData['notifications'] as List,
      );
    }
    _featureResult = null;
    if (mounted) setState(() => _section = index);
  });

  Future<void> _runFeatureAction(
    FeatureAction action, {
    Map<String, String>? pathOverrides,
    Map<String, dynamic>? bodyOverrides,
    Map<String, dynamic>? initialValues,
  }) async {
    if (action.path == '/api/site-manager/connect') {
      await _chooseSiteFolder();
      return;
    }
    final record =
        initialValues ??
        (action.path == '/api/site-manager/site'
            ? (_featureData['site'] as Map?)?.cast<String, dynamic>()
            : null);
    final payload = actionInitialValues(action, record: record);
    if (bodyOverrides != null) payload.addAll(bodyOverrides);
    final hiddenBodyKeys = bodyOverrides?.keys.toSet() ?? <String>{};
    if (action.path == '/api/social/buffer/posts' &&
        _bufferPublicImageUrl != null) {
      payload['image_url'] = _bufferPublicImageUrl;
    }
    final pathFields = <String, TextEditingController>{};
    final pathSelected = <String, String?>{};
    final choiceLabels = <String, List<({String value, String label})>>{};
    for (final match in RegExp(r':([a-zA-Z_]+)').allMatches(action.path)) {
      final key = match.group(1)!;
      if (pathOverrides?[key]?.trim().isNotEmpty ?? false) continue;
      final options = _idOptions(key);
      if (options.isNotEmpty) {
        choiceLabels[key] = options;
        pathSelected[key] = options.length == 1 ? options.first.value : null;
      } else {
        pathFields[key] = TextEditingController();
      }
    }
    final dataFields = <String, TextEditingController>{};
    final nestedFields = <String, Map<String, TextEditingController>>{};
    final boolValues = <String, bool>{};
    final dropdownValues = <String, String?>{};
    final dropdownOptions = <String, List<String>>{};
    for (final entry in payload.entries) {
      if (hiddenBodyKeys.contains(entry.key)) continue;
      final spec = action.specFor(entry.key);
      if (entry.value is Map && spec == null) {
        final sub = <String, TextEditingController>{};
        for (final subEntry in flattenFormObject(entry.value as Map).entries) {
          sub[subEntry.key.toString()] = TextEditingController(
            text: subEntry.value?.toString() ?? '',
          );
        }
        nestedFields[entry.key] = sub;
        continue;
      }
      if (spec?.type == FieldType.boolean) {
        boolValues[entry.key] = entry.value == true;
        continue;
      }
      if (spec?.type == FieldType.dropdown) {
        final options = spec!.options;
        final initial = entry.value?.toString() ?? '';
        dropdownOptions[entry.key] = options;
        dropdownValues[entry.key] = options.contains(initial)
            ? initial
            : (options.isEmpty ? null : options.first);
        continue;
      }
      if (spec?.type == FieldType.integer) {
        final options = _idOptions(entry.key);
        if (options.isNotEmpty) {
          choiceLabels[entry.key] = options;
          dropdownOptions[entry.key] = options.map((o) => o.value).toList();
          dropdownValues[entry.key] = options.length == 1
              ? options.first.value
              : null;
          continue;
        }
      }
      if (entry.key == 'path' && _section == 1) {
        final options = _studioFileOptions();
        if (options.isNotEmpty) {
          choiceLabels[entry.key] = options;
          dropdownOptions[entry.key] = options.map((o) => o.value).toList();
          final initial = entry.value?.toString() ?? '';
          dropdownValues[entry.key] = options.any((o) => o.value == initial)
              ? initial
              : null;
          continue;
        }
      }
      dataFields[entry.key] = TextEditingController(
        text: entry.value is Map || entry.value is List
            ? const JsonEncoder.withIndent('  ').convert(entry.value)
            : entry.value?.toString() ?? '',
      );
    }
    final submitted = await showDialog<(String, Map<String, dynamic>)>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(
            action.label,
            style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w600),
          ),
          content: SizedBox(
            width: 500,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 560),
              child: ListView(
                shrinkWrap: true,
                children: [
                  if (action.help.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 14),
                      child: Text(
                        action.help,
                        style: const TextStyle(
                          color: _secondaryInk,
                          height: 1.4,
                        ),
                      ),
                    ),
                  ..._pathFieldWidgets(
                    action,
                    pathFields,
                    pathSelected,
                    choiceLabels,
                    setDialogState,
                  ),
                  if (action.uploadField == null && action.method != 'GET')
                    ..._bodyFieldWidgets(
                      context,
                      action,
                      payload,
                      dataFields,
                      nestedFields,
                      boolValues,
                      dropdownValues,
                      dropdownOptions,
                      choiceLabels,
                      setDialogState,
                    ),
                  if (action.uploadField != null)
                    const Text(
                      'Choose a file from this Mac. ONEBoard uploads it to your connected workspace.',
                      style: TextStyle(color: _secondaryInk),
                    ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () {
                if (pathFields.values.any(
                  (field) => field.text.trim().isEmpty,
                )) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('Enter the required item ID first.'),
                    ),
                  );
                  return;
                }
                for (final entry in pathSelected.entries) {
                  if ((entry.value ?? '').isEmpty) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(
                          'Choose ${_humanize(entry.key).toLowerCase()} first.',
                        ),
                      ),
                    );
                    return;
                  }
                }
                var resolvedPath = action.path;
                pathOverrides?.forEach((key, value) {
                  resolvedPath = resolvedPath.replaceAll(
                    ':$key',
                    Uri.encodeComponent(value.trim()),
                  );
                });
                for (final entry in pathFields.entries) {
                  resolvedPath = resolvedPath.replaceAll(
                    ':${entry.key}',
                    Uri.encodeComponent(entry.value.text.trim()),
                  );
                }
                for (final entry in pathSelected.entries) {
                  resolvedPath = resolvedPath.replaceAll(
                    ':${entry.key}',
                    Uri.encodeComponent(entry.value!.trim()),
                  );
                }
                final values = <String, dynamic>{};
                if (bodyOverrides != null) values.addAll(bodyOverrides);
                for (final entry in nestedFields.entries) {
                  final originalSub = flattenFormObject(
                    payload[entry.key] as Map,
                  );
                  final subValues = <String, dynamic>{};
                  for (final sub in entry.value.entries) {
                    final initial = originalSub[sub.key];
                    try {
                      subValues[sub.key] = coerceFieldValue(
                        null,
                        initial,
                        sub.value.text,
                      );
                    } on FormatException {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text('${_humanize(sub.key)} is invalid.'),
                        ),
                      );
                      return;
                    }
                  }
                  values[entry.key] = expandFormObject(subValues);
                }
                for (final entry in boolValues.entries) {
                  values[entry.key] = entry.value;
                }
                for (final entry in dropdownValues.entries) {
                  final selected = entry.value;
                  if (selected == null || selected.isEmpty) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(
                          'Choose ${_humanize(entry.key).toLowerCase()}.',
                        ),
                      ),
                    );
                    return;
                  }
                  try {
                    values[entry.key] = coerceFieldValue(
                      action.specFor(entry.key),
                      payload[entry.key],
                      selected,
                    );
                  } on FormatException catch (error) {
                    ScaffoldMessenger.of(
                      context,
                    ).showSnackBar(SnackBar(content: Text(error.message)));
                    return;
                  }
                }
                if (action.path == '/api/settings/ai-policy') {
                  values['provider'] = 'muse';
                }
                for (final entry in dataFields.entries) {
                  try {
                    values[entry.key] = coerceFieldValue(
                      action.specFor(entry.key),
                      payload[entry.key],
                      entry.value.text,
                    );
                  } on FormatException catch (error) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(
                          error.message.isEmpty
                              ? '${_humanize(entry.key)} is invalid.'
                              : error.message,
                        ),
                      ),
                    );
                    return;
                  }
                }
                Navigator.pop(dialogContext, (resolvedPath, values));
              },
              child: Text(
                action.uploadField == null
                    ? (action.method == 'GET' ? 'Open' : 'Run action')
                    : 'Choose file',
              ),
            ),
          ],
        ),
      ),
    );
    for (final controller in pathFields.values) {
      controller.dispose();
    }
    for (final controller in dataFields.values) {
      controller.dispose();
    }
    for (final sub in nestedFields.values) {
      for (final controller in sub.values) {
        controller.dispose();
      }
    }
    if (submitted == null || !mounted) return;
    await _action(() async {
      Map<String, dynamic> result;
      if (action.uploadField != null) {
        final filePath = await _serviceChannel.invokeMethod<String>(
          'chooseFile',
        );
        if (filePath == null) return;
        result = await _api!.upload(
          submitted.$1,
          action.uploadField!,
          filePath,
        );
        if (submitted.$1 == '/api/social/images/upload') {
          final image = (result['image'] as Map?) ?? const {};
          final libraryUrl = image['url']?.toString() ?? '';
          if (libraryUrl.isEmpty) {
            throw Exception('The image service returned no image.');
          }
          final mirror = await _api!.post('/api/social/images/mirror', {
            'image_url': libraryUrl,
          });
          final publicUrl = mirror['url']?.toString() ?? '';
          if (publicUrl.isEmpty) {
            throw Exception('The media server returned no public URL.');
          }
          _bufferPublicImageUrl = publicUrl;
          result['buffer_public_url'] = publicUrl;
          result['buffer_image_note'] =
              'Buffer will download the public copy from your media server.';
        }
      } else {
        Map<String, dynamic>? payload;
        if (submitted.$2.isNotEmpty) {
          payload = submitted.$2;
        }
        if (payload != null &&
            submitted.$1.startsWith('/api/site-manager/') &&
            _workspacePath.isNotEmpty) {
          payload.putIfAbsent('expected_directory_path', () => _workspacePath);
        }
        result = action.label == 'Prepare repair'
            ? await prepareSecurityRepair(_api!, submitted.$1)
            : await _api!.call(action.method, submitted.$1, payload);
      }
      if (result['auth_url'] is String) {
        await _openExternal(result['auth_url'] as String);
      }
      _featureResult = result;
      if (_section == 1) {
        await _browseSite(_sitePath, keepResult: true);
        _featureResult = result;
        if (mounted) setState(() {});
      } else {
        final page = featurePages[_section - 1];
        _featureData = await _api!.get(page.endpoint);
      }
    });
    if (_error == null &&
        action.label == 'Prepare repair' &&
        _featureResult?['prompt'] is String) {
      final prompt = _featureResult!['prompt'];
      await _loadSites();
      if (!mounted) return;
      await _runFeatureAction(
        featurePages.first.actions.firstWhere(
          (a) => a.label == 'Run site assistant',
        ),
        initialValues: {'prompt': prompt},
      );
    }
  }

  /// Files in the current Studio folder as dropdown options, so destructive
  /// actions like delete never need a typed path.
  List<({String value, String label})> _studioFileOptions() {
    final manager = (_sites['manager'] as Map?)?.cast<String, dynamic>() ?? {};
    final files = (manager['files'] as Map?)?.cast<String, dynamic>() ?? {};
    final entries = (files['entries'] as List?)?.whereType<Map>().toList() ?? [];
    final options = <({String value, String label})>[];
    for (final item in entries) {
      final map = item.cast<String, dynamic>();
      if (map['is_dir'] == true || map['type'] == 'directory') continue;
      final path = map['path']?.toString() ?? '';
      if (path.isEmpty) continue;
      options.add(
        (value: path, label: map['name']?.toString() ?? path),
      );
    }
    return options;
  }

  List<({String value, String label})> _idOptions(String fieldName) {
    final base = fieldName.endsWith('_id')
        ? fieldName.substring(0, fieldName.length - 3)
        : fieldName;
    final sources = <Map<String, dynamic>>[];
    if (_section == 1) {
      sources.add((_sites['manager'] as Map?)?.cast<String, dynamic>() ?? {});
    } else {
      sources.add(_featureData);
      final manager = (_featureData['manager'] as Map?)
          ?.cast<String, dynamic>();
      if (manager != null) sources.add(manager);
    }
    for (final source in sources) {
      for (final entry in source.entries) {
        if (entry.value is! List) continue;
        if (!entry.key.toLowerCase().contains(base.toLowerCase())) continue;
        final items = (entry.value as List).whereType<Map>().toList();
        if (items.isEmpty) continue;
        final options = <({String value, String label})>[];
        for (final item in items) {
          final map = item.cast<String, dynamic>();
          final id = map['id'] ?? map[fieldName] ?? map['${base}_id'];
          if (id == null || id.toString().isEmpty) continue;
          options.add((
            value: id.toString(),
            label: '${_entryTitle(map)} ($id)',
          ));
        }
        if (options.isNotEmpty) return options;
      }
    }
    return [];
  }

  List<Widget> _pathFieldWidgets(
    FeatureAction action,
    Map<String, TextEditingController> pathFields,
    Map<String, String?> pathSelected,
    Map<String, List<({String value, String label})>> choiceLabels,
    StateSetter setDialogState,
  ) {
    final widgets = <Widget>[];
    final keys = RegExp(r':([a-zA-Z_]+)')
        .allMatches(action.path)
        .map((match) => match.group(1)!)
        .where(
          (key) => pathFields.containsKey(key) || pathSelected.containsKey(key),
        )
        .toList();
    for (var index = 0; index < keys.length; index++) {
      final key = keys[index];
      if (pathSelected.containsKey(key)) {
        final choices = choiceLabels[key] ?? [];
        widgets.add(
          Padding(
            padding: const EdgeInsets.only(bottom: 11),
            child: DropdownButtonFormField<String>(
              initialValue: pathSelected[key],
              hint: Text('Choose ${_humanize(key).toLowerCase()}'),
              items: [
                for (final choice in choices)
                  DropdownMenuItem(
                    value: choice.value,
                    child: Text(choice.label, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: (value) =>
                  setDialogState(() => pathSelected[key] = value),
              decoration: InputDecoration(labelText: _humanize(key)),
            ),
          ),
        );
      } else {
        final spec = action.specFor(key);
        widgets.add(
          Padding(
            padding: const EdgeInsets.only(bottom: 11),
            child: TextField(
              controller: pathFields[key],
              autofocus: index == 0,
              keyboardType: spec?.type == FieldType.integer
                  ? TextInputType.number
                  : null,
              decoration: InputDecoration(
                labelText: _humanize(key),
                hintText: 'Enter ${_humanize(key).toLowerCase()}',
              ),
            ),
          ),
        );
      }
    }
    return widgets;
  }

  List<Widget> _bodyFieldWidgets(
    BuildContext context,
    FeatureAction action,
    Map<String, dynamic> payload,
    Map<String, TextEditingController> dataFields,
    Map<String, Map<String, TextEditingController>> nestedFields,
    Map<String, bool> boolValues,
    Map<String, String?> dropdownValues,
    Map<String, List<String>> dropdownOptions,
    Map<String, List<({String value, String label})>> choiceLabels,
    StateSetter setDialogState,
  ) {
    final widgets = <Widget>[];
    for (final key in payload.keys) {
      if (nestedFields.containsKey(key)) {
        final sub = nestedFields[key]!;
        widgets.add(
          Padding(
            padding: const EdgeInsets.only(bottom: 11),
            child: Container(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 4),
              decoration: BoxDecoration(
                color: const Color(0xFFF9F9FB),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _humanize(key),
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: boardInk,
                    ),
                  ),
                  const SizedBox(height: 10),
                  for (final subEntry in sub.entries)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: TextField(
                        controller: subEntry.value,
                        decoration: InputDecoration(
                          labelText: _humanize(subEntry.key),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        );
        continue;
      }
      if (boolValues.containsKey(key)) {
        widgets.add(
          Padding(
            padding: const EdgeInsets.only(bottom: 11),
            child: SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(_humanize(key)),
              value: boolValues[key]!,
              onChanged: (value) =>
                  setDialogState(() => boolValues[key] = value),
            ),
          ),
        );
        continue;
      }
      if (dropdownValues.containsKey(key)) {
        final options = dropdownOptions[key] ?? [];
        final choices = choiceLabels[key];
        String labelFor(String option) {
          if (choices != null) {
            for (final choice in choices) {
              if (choice.value == option) return choice.label;
            }
          }
          return _humanize(option);
        }

        widgets.add(
          Padding(
            padding: const EdgeInsets.only(bottom: 11),
            child: DropdownButtonFormField<String>(
              initialValue: dropdownValues[key],
              hint: Text('Choose ${_humanize(key).toLowerCase()}'),
              items: [
                for (final option in options)
                  DropdownMenuItem(
                    value: option,
                    child: Text(
                      labelFor(option),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
              onChanged: (value) =>
                  setDialogState(() => dropdownValues[key] = value),
              decoration: InputDecoration(labelText: _humanize(key)),
            ),
          ),
        );
        continue;
      }
      final controller = dataFields[key];
      if (controller == null) continue;
      final spec = action.specFor(key);
      final type = spec?.type;
      final obscure =
          type == FieldType.password ||
          (spec == null &&
              (key.contains('password') || key.contains('api_key')));
      final multiline =
          type == FieldType.multiline || controller.text.contains('\n');
      if (type == FieldType.folder || type == FieldType.file) {
        final isFolder = type == FieldType.folder;
        widgets.add(
          Padding(
            padding: const EdgeInsets.only(bottom: 11),
            child: TextField(
              controller: controller,
              readOnly: true,
              onTap: () => _pickDialogPath(
                context,
                controller,
                folder: isFolder,
              ),
              decoration: InputDecoration(
                labelText: _humanize(key),
                hintText: isFolder
                    ? 'Tap to choose a folder…'
                    : 'Tap to choose a file…',
                suffixIcon: Icon(
                  isFolder
                      ? Icons.folder_open_outlined
                      : Icons.insert_drive_file_outlined,
                ),
              ),
            ),
          ),
        );
        continue;
      }
      if (type == FieldType.date || type == FieldType.month) {
        widgets.add(
          Padding(
            padding: const EdgeInsets.only(bottom: 11),
            child: TextField(
              controller: controller,
              readOnly: true,
              onTap: () => _pickDialogDate(
                context,
                controller,
                monthOnly: type == FieldType.month,
              ),
              decoration: InputDecoration(
                labelText: _humanize(key),
                hintText: type == FieldType.month ? 'YYYY-MM' : 'YYYY-MM-DD',
                suffixIcon: const Icon(Icons.calendar_month_outlined),
              ),
            ),
          ),
        );
        continue;
      }
      widgets.add(
        Padding(
          padding: const EdgeInsets.only(bottom: 11),
          child: TextField(
            controller: controller,
            obscureText: obscure,
            enableSuggestions: !obscure,
            autocorrect: !obscure,
            keyboardType: type == FieldType.integer
                ? TextInputType.number
                : type == FieldType.stringList
                ? TextInputType.text
                : null,
            minLines: multiline
                ? 3
                : type == FieldType.stringList
                ? 2
                : 1,
            maxLines: multiline || type == FieldType.stringList ? 6 : 1,
            decoration: InputDecoration(
              labelText: _humanize(key),
              alignLabelWithHint: true,
              helperText: spec?.hint.isNotEmpty ?? false ? spec!.hint : null,
              helperMaxLines: 3,
            ),
          ),
        ),
      );
    }
    return widgets;
  }

  Future<void> _pickDialogPath(
    BuildContext context,
    TextEditingController controller, {
    required bool folder,
  }) async {
    try {
      final path = await _serviceChannel.invokeMethod<String>(
        folder ? 'chooseDirectory' : 'chooseFile',
      );
      if (path != null && path.isNotEmpty) controller.text = path;
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not open the file picker.')),
        );
      }
    }
  }

  Future<void> _pickDialogDate(
    BuildContext context,
    TextEditingController controller, {
    required bool monthOnly,
  }) async {
    final now = DateTime.now();
    final current = DateTime.tryParse(controller.text.trim());
    final picked = await showDatePicker(
      context: context,
      initialDate: current ?? now,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null) return;
    final formatted =
        '${picked.year.toString().padLeft(4, '0')}-'
        '${picked.month.toString().padLeft(2, '0')}'
        '${monthOnly ? '' : '-${picked.day.toString().padLeft(2, '0')}'}';
    controller.text = formatted;
  }

  Future<void> _logout() => _action(() async {
    await _api!.post('/api/auth/logout');
    await FirebaseWorkspace.instance.signOut();
    setState(() {
      _authenticated = false;
      _userName = '';
    });
  });

  /// Best-effort device registration so the local backend can send push.
  Future<void> _registerPushDevice(String token) async {
    final api = _api;
    if (api == null || !_authenticated || token.isEmpty) return;
    try {
      await api.post('/api/notifications/device', {
        'token': token,
        'platform': 'macos',
      });
    } catch (_) {
      // Push registration never blocks the session.
    }
  }

  void _showPushMessage(String title, String body) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('$title · $body'),
        action: SnackBarAction(
          label: 'View',
          onPressed: () => _loadFeature(13),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_connected) return _serviceUnavailableView();
    if (!_authenticated) return _loginView();
    return Scaffold(
      body: CallbackShortcuts(
        bindings: {
          const SingleActivator(LogicalKeyboardKey.keyK, meta: true): _openSearch,
          const SingleActivator(LogicalKeyboardKey.keyK, control: true):
              _openSearch,
        },
        child: Focus(
          autofocus: true,
          child: WorkspaceChrome(
            userName: _userName,
            selectedSection: _section,
            busy: _busy,
            usingCachedData: _usingCachedData,
            onLogout: _logout,
            onNavigate: _navigate,
            onRefresh: _refreshSection,
            onSearch: _openSearch,
            child: Column(
              children: [
                if (_error != null) _errorBanner(_error!),
                Expanded(
                  child: _busy
                      ? const Center(child: CircularProgressIndicator())
                      : _content(),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _openSearch() {
    if (_busy) return;
    showDialog<void>(
      context: context,
      builder: (context) => SearchPalette(
        onPickSection: (section) => _navigate(section),
        onPickAction: (section, action) async {
          await _navigate(section);
          if (!mounted) return;
          await _runFeatureAction(action);
        },
      ),
    );
  }

  Future<void> _navigate(int index) async {
    if (index == 15) {
      setState(() => _section = index);
    } else if (index == 0) {
      await _loadDashboard();
    } else if (index == 1) {
      await _loadSites();
    } else {
      await _loadFeature(index);
    }
  }

  void _refreshSection() {
    if (_section == 0) _loadDashboard();
    if (_section == 1) _loadSites();
    if (_section >= 2 && _section < 15) _loadFeature(_section);
  }

  Widget _content() => Padding(
    padding: const EdgeInsets.fromLTRB(30, 26, 30, 28),
    child: switch (_section) {
      0 => _dashboardView(),
      1 => _sitesView(),
      2 => _previewView(),
      3 => _siteBrandView(),
      4 => _healthView(),
      6 => _calendarView(),
      10 => _socialView(),
      11 => _teamsView(),
      14 => _settingsView(),
      15 => _helpView(),
      _ => _featureView(),
    },
  );

  Widget _dashboardView() => WorkspaceDashboard(
    data: _dashboard,
    userName: _userName,
    onConnect: _chooseSiteFolder,
    onOpenStudio: _loadSites,
    onNavigate: _navigate,
    searchConsole: SearchConsolePanel(
      data: (_dashboard['gsc'] as Map?)?.cast<String, dynamic>() ?? {},
      busy: _busy || _usingCachedData,
      onConnect: _connectSearchConsole,
      onDisconnect: _disconnectSearchConsole,
      onRefresh: () => _action(_refreshSearchConsole),
      onSelectProperty: _selectSearchProperty,
      onCreatePage: _createSearchPage,
    ),
  );

  Widget _sitesView() {
    final manager = (_sites['manager'] as Map?)?.cast<String, dynamic>() ?? {};
    final files = (manager['files'] as Map?)?.cast<String, dynamic>() ?? {};
    final directory =
        (manager['directory'] as Map?)?.cast<String, dynamic>() ?? {};
    final entries = (files['entries'] as List?) ?? [];
    final current = directory['path']?.toString() ?? 'No folder connected';
    return ListView(
      children: [
        if (_featureResult != null) ...[
          ActionResultCard(
            result: _featureResult!,
            detailsBuilder: _detailValue,
            onOpenLink: _openExternal,
          ),
          const SizedBox(height: 16),
        ],
        const Text(
          'Site Studio',
          style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 7),
        const Text(
          'Browse your connected site and manage its content.',
          style: TextStyle(color: Color(0xFF5B6B73)),
        ),
        const SizedBox(height: 22),
        _panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Active folder',
                style: TextStyle(color: Color(0xFF5B6B73), fontSize: 12),
              ),
              const SizedBox(height: 7),
              Row(
                children: [
                  const Icon(CupertinoIcons.folder, color: cyan),
                  const SizedBox(width: 10),
                  Expanded(child: SelectableText(current)),
                  if (_sitePath.isNotEmpty)
                    IconButton(
                      tooltip: 'Go up one level',
                      onPressed: () =>
                          _browseSite(files['parent_path']?.toString() ?? ''),
                      icon: const Icon(Icons.arrow_upward_rounded),
                    ),
                  const SizedBox(width: 6),
                  OutlinedButton.icon(
                    onPressed: _chooseSiteFolder,
                    icon: const Icon(CupertinoIcons.folder, size: 16),
                    label: const Text('Choose folder'),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        if (manager['projects'] is List) ...[
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final project
                  in (manager['projects'] as List).whereType<Map>())
                ActionChip(
                  avatar: const Icon(Icons.folder_outlined, size: 16),
                  label: Text(
                    '${project['display_name'] ?? project['name'] ?? project['path'] ?? 'Project'}',
                  ),
                  onPressed: _busy
                      ? null
                      : () => _action(() async {
                          await _api!.post('/api/site-manager/connect', {
                            'project_id': project['id'],
                          });
                          await _browseSite('');
                        }),
                ),
            ],
          ),
          const SizedBox(height: 14),
        ],
        _actionList(featurePages.first),
        const SizedBox(height: 14),
        if (entries.isEmpty)
          _panel(
            child: const Padding(
              padding: EdgeInsets.all(13),
              child: Text(
                'There are no files to display. Connect a site folder to get started.',
                style: TextStyle(color: Color(0xFF5B6B73)),
              ),
            ),
          )
        else
          ...entries.map((item) {
            final entry = item is Map ? item : <String, dynamic>{'name': item};
            final isDir =
                entry['is_dir'] == true || entry['type'] == 'directory';
            final name =
                entry['name']?.toString() ??
                entry['path']?.toString() ??
                'Item';
            final meta = [
              entry['size_label']?.toString() ?? '',
              entry['modified_at']?.toString() ?? '',
            ].where((part) => part.isNotEmpty && part != '-').join(' · ');
            return Padding(
              padding: const EdgeInsets.only(bottom: 7),
              child: _panel(
                child: InkWell(
                  onTap: isDir
                      ? () => _browseSite(entry['path']?.toString() ?? '')
                      : () => _openStudioFile(entry),
                  borderRadius: BorderRadius.circular(8),
                  child: Row(
                    children: [
                      Icon(
                        isDir
                            ? Icons.folder_rounded
                            : Icons.insert_drive_file_outlined,
                        color: isDir ? cyan : const Color(0xFF5B6B73),
                        size: 19,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(name),
                            if (!isDir && meta.isNotEmpty)
                              Padding(
                                padding: const EdgeInsets.only(top: 2),
                                child: Text(
                                  meta,
                                  style: const TextStyle(
                                    color: Color(0xFF74838A),
                                    fontSize: 11,
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                      Text(
                        isDir ? 'Folder' : 'File',
                        style: const TextStyle(
                          color: Color(0xFF74838A),
                          fontSize: 12,
                        ),
                      ),
                      if (!isDir) ...[
                        const SizedBox(width: 4),
                        PopupMenuButton<String>(
                          tooltip: 'File actions',
                          icon: const Icon(
                            Icons.more_horiz,
                            size: 18,
                            color: _secondaryInk,
                          ),
                          onSelected: (value) =>
                              _studioFileAction(entry, value),
                          itemBuilder: (context) => [
                            const PopupMenuItem(
                              value: 'open',
                              child: Text('Open'),
                            ),
                            if (isHtmlFile(name))
                              const PopupMenuItem(
                                value: 'preview',
                                child: Text('Open in Preview'),
                              ),
                            const PopupMenuItem(
                              value: 'assistant',
                              child: Text('Ask assistant about file'),
                            ),
                            const PopupMenuItem(
                              value: 'terminal',
                              child: Text('Run command on file'),
                            ),
                            const PopupMenuItem(
                              value: 'delete',
                              child: Text('Delete'),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            );
          }),
        ..._studioBackupsSection(manager),
        ..._studioUpdatesSection(manager),
        ..._studioTeamNote(manager),
        ..._studioAssetsSection(manager),
        ..._studioAssistantSection(manager),
        ..._studioRemoteSection(manager),
      ],
    );
  }

  List<Widget> _studioTeamNote(Map<String, dynamic> manager) {
    final context =
        (manager['team_context'] as Map?)?.cast<String, dynamic>();
    if (context == null) return [];
    return [
      const SizedBox(height: 20),
      _panel(
        child: Row(
          children: [
            const Icon(Icons.group_outlined, size: 18, color: _secondaryInk),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                teamShareLabel(context),
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: _ink,
                ),
              ),
            ),
          ],
        ),
      ),
    ];
  }

  List<Widget> _studioAssetsSection(Map<String, dynamic> manager) {
    final assets =
        (manager['assets'] as List?)?.whereType<Map>().toList() ?? [];
    final upload = featurePages.first.actions.firstWhere(
      (item) => item.label == 'Upload site image',
    );
    return [
      const SizedBox(height: 20),
      Row(
        children: [
          Expanded(
            child: Text(
              'Site images (${assets.length})',
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
            ),
          ),
          OutlinedButton.icon(
            onPressed: _busy || _api == null
                ? null
                : () => _runFeatureAction(upload),
            icon: const Icon(Icons.upload_outlined, size: 16),
            label: const Text('Upload'),
          ),
        ],
      ),
      const SizedBox(height: 9),
      if (assets.isEmpty)
        _panel(
          child: const Padding(
            padding: EdgeInsets.all(13),
            child: Text(
              'No site images yet. Upload PNG, JPEG, GIF, or WebP files.',
              style: TextStyle(color: Color(0xFF5B6B73)),
            ),
          ),
        )
      else
        _panel(
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final asset in assets) ...[
                  AssetThumb(
                    api: _api!,
                    asset: asset.cast<String, dynamic>(),
                  ),
                  const SizedBox(width: 12),
                ],
              ],
            ),
          ),
        ),
    ];
  }

  List<Widget> _studioAssistantSection(Map<String, dynamic> manager) {
    final prompts =
        (manager['quick_prompts'] as Map?)?.cast<String, dynamic>() ?? {};
    final messages =
        (manager['codex_messages'] as List?)?.whereType<Map>().toList() ?? [];
    final codex = featurePages.first.actions.firstWhere(
      (item) => item.label == 'Run site assistant',
    );
    final recent = messages.reversed.take(8).toList();
    return [
      const SizedBox(height: 20),
      const Text(
        'Assistant',
        style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
      ),
      const SizedBox(height: 9),
      if (prompts.isNotEmpty)
        _panel(
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final entry in prompts.entries)
                OutlinedButton(
                  onPressed: _busy
                      ? null
                      : () => _runFeatureAction(
                          codex,
                          bodyOverrides: {
                            'prompt': entry.value?.toString() ?? '',
                          },
                        ),
                  child: Text(quickPromptLabel(entry.key.toString())),
                ),
            ],
          ),
        ),
      if (recent.isNotEmpty) ...[
        const SizedBox(height: 9),
        for (final item in recent)
          _studioItemCard(
            title:
                '${(item['role']?.toString() ?? 'assistant')[0].toUpperCase()}${(item['role']?.toString() ?? 'assistant').substring(1)}',
            subtitle: item['created_at']?.toString() ?? '',
            actions: const [],
            body: item['content']?.toString() ?? '',
          ),
      ],
    ];
  }

  List<Widget> _studioRemoteSection(Map<String, dynamic> manager) {
    final remote =
        (manager['remote_connection'] as Map?)?.cast<String, dynamic>();
    final ssh = (manager['ssh_key'] as Map?)?.cast<String, dynamic>() ?? {};
    final studio = featurePages.first;
    FeatureAction named(String label) =>
        studio.actions.firstWhere((item) => item.label == label);
    final widgets = <Widget>[
      const SizedBox(height: 20),
      const Text(
        'Remote publishing',
        style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
      ),
      const SizedBox(height: 9),
    ];
    if (remote == null) {
      widgets.add(
        _studioItemCard(
          title: 'Not connected',
          subtitle: 'Publish this site to a remote server over SSH.',
          actions: [
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _runFeatureAction(named('Save remote connection')),
              child: const Text('Set up'),
            ),
          ],
        ),
      );
    } else {
      final target =
          '${remote['username'] ?? ''}@${remote['host'] ?? ''}:${remote['port'] ?? 22}${remote['remote_path'] ?? ''}';
      widgets.add(
        _studioItemCard(
          title: target,
          subtitle: 'Auth: ${remote['auth_method'] ?? 'key'}',
          actions: [
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _runFeatureAction(named('Sync remote site')),
              child: const Text('Sync now'),
            ),
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _runFeatureAction(named('Test remote connection')),
              child: const Text('Test'),
            ),
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _runFeatureAction(named('Save remote connection')),
              child: const Text('Edit'),
            ),
          ],
        ),
      );
    }
    if (ssh['exists'] == true) {
      widgets.add(
        _studioItemCard(
          title: 'SSH key ready',
          subtitle: 'Use this public key on your server.',
          actions: const [],
          body: ssh['public_key']?.toString() ?? '',
        ),
      );
    } else {
      widgets.add(
        _studioItemCard(
          title: 'No SSH key',
          subtitle: 'Create one to enable key-based publishing.',
          actions: [
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _runFeatureAction(named('Create SSH key')),
              child: const Text('Create SSH key'),
            ),
          ],
        ),
      );
    }
    return widgets;
  }

  void _openStudioFile(Map entry) {
    final api = _api;
    if (api == null) return;
    final path = entry['path']?.toString() ?? '';
    final name = entry['name']?.toString() ?? path;
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => StudioFileView(
          api: api,
          filePath: path,
          displayName: name,
          onOpenPreview: (previewPath) => _openPreview(path: previewPath),
        ),
      ),
    );
  }

  void _studioFileAction(Map entry, String value) {
    final path = entry['path']?.toString() ?? '';
    final studio = featurePages.first;
    FeatureAction named(String label) =>
        studio.actions.firstWhere((item) => item.label == label);
    switch (value) {
      case 'open':
        _openStudioFile(entry);
      case 'preview':
        _openPreview(path: path);
      case 'delete':
        _runFeatureAction(named('Delete file'), bodyOverrides: {'path': path});
      case 'terminal':
        _runFeatureAction(
          named('Run terminal command'),
          bodyOverrides: {
            'command': "cat -- '${path.replaceAll("'", "'\"'\"'")}'",
          },
        );
      case 'assistant':
        _runFeatureAction(
          named('Run site assistant'),
          bodyOverrides: {
            'prompt': 'Review the file $path and suggest improvements.',
          },
        );
    }
  }

  List<Widget> _studioBackupsSection(Map<String, dynamic> manager) {
    final backups =
        (manager['backups'] as List?)?.whereType<Map>().toList() ?? [];
    if (backups.isEmpty) return [];
    final restore = featurePages.first.actions.firstWhere(
      (item) => item.label == 'Restore backup',
    );
    return [
      const SizedBox(height: 20),
      Text(
        'Backups (${backups.length})',
        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
      ),
      const SizedBox(height: 9),
      for (final item in backups)
        _studioItemCard(
          title: item['filename']?.toString() ?? 'Backup ${item['id']}',
          subtitle: [
            item['size_label']?.toString() ?? '',
            item['created_at']?.toString() ?? '',
            item['author_name']?.toString() ?? '',
          ].where((part) => part.isNotEmpty).join(' · '),
          actions: [
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _runFeatureAction(
                      restore,
                      bodyOverrides: {'backup_id': item['id']},
                    ),
              child: const Text('Restore'),
            ),
          ],
        ),
    ];
  }

  List<Widget> _studioUpdatesSection(Map<String, dynamic> manager) {
    final updates =
        (manager['updates'] as List?)?.whereType<Map>().toList() ?? [];
    if (updates.isEmpty) return [];
    final studio = featurePages.first;
    FeatureAction named(String label) =>
        studio.actions.firstWhere((item) => item.label == label);
    return [
      const SizedBox(height: 20),
      Text(
        'Updates (${updates.length})',
        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
      ),
      const SizedBox(height: 9),
      for (final item in updates)
        _studioItemCard(
          title: item['summary']?.toString() ?? 'Update ${item['id']}',
          subtitle: [
            item['status']?.toString() ?? '',
            item['created_at']?.toString() ?? '',
          ].where((part) => part.isNotEmpty).join(' · '),
          actions: [
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _runFeatureAction(
                      named('Approve update'),
                      bodyOverrides: {
                        'update_id': item['id'],
                        'action': 'approve',
                      },
                    ),
              child: const Text('Approve'),
            ),
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _runFeatureAction(
                      named('Publish update remotely'),
                      bodyOverrides: {
                        'update_id': item['id'],
                        'action': 'publish',
                      },
                    ),
              child: const Text('Publish'),
            ),
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _runFeatureAction(
                      named('Restore update'),
                      bodyOverrides: {
                        'update_id': item['id'],
                        'action': 'restore',
                      },
                    ),
              child: const Text('Restore'),
            ),
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _openPreview(updateId: int.tryParse('${item['id']}')),
              child: const Text('Compare'),
            ),
          ],
        ),
    ];
  }

  Widget _studioItemCard({
    required String title,
    required String subtitle,
    required List<Widget> actions,
    String body = '',
  }) => Padding(
    padding: const EdgeInsets.only(bottom: 9),
    child: _panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: _ink,
            ),
          ),
          if (subtitle.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              subtitle,
              style: const TextStyle(fontSize: 12, color: _secondaryInk),
            ),
          ],
          if (body.isNotEmpty) ...[
            const SizedBox(height: 8),
            Container(
              constraints: const BoxConstraints(maxHeight: 160),
              child: SingleChildScrollView(
                child: SelectableText(
                  body,
                  style: const TextStyle(fontSize: 12.5, height: 1.5),
                ),
              ),
            ),
          ],
          if (actions.isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(spacing: 8, runSpacing: 8, children: actions),
          ],
        ],
      ),
    ),
  );

  Widget _calendarView() {
    final page = featurePages[5];
    return ListView(
      children: [
        const Text(
          'Calendar',
          style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 16),
        if (_featureResult != null)
          ActionResultCard(
            result: _featureResult!,
            detailsBuilder: _detailValue,
            onOpenLink: _openExternal,
          ),
        CalendarPanel(
          events: ((_featureData['events'] as List?) ?? [])
              .whereType<Map>()
              .map((e) => e.cast<String, dynamic>())
              .toList(),
          busy: _busy || _usingCachedData,
          onCreate: (date) => _runFeatureAction(
            page.actions.first,
            initialValues: {'starts_on': date},
          ),
          recordBuilder: (event) => _recordCard(page, 'events', event),
        ),
      ],
    );
  }

  Widget _featureView() {
    final page = featurePages[_section - 1];
    return ListView(children: _featureChildren(page, _featureData));
  }

  Widget _previewView() {
    final page = featurePages[1];
    return ListView(
      children: [
        PreviewPanel(
          key: ValueKey('preview-$_previewPath-${_previewUpdateId ?? 'none'}'),
          api: _api!,
          workspacePath: _workspacePath,
          initialPath: _previewPath,
          initialUpdateId: _previewUpdateId,
          onAssistantResult: (result) {
            if (mounted) setState(() => _featureResult = result);
          },
        ),
        const SizedBox(height: 18),
        ..._featureChildren(page, _featureData),
      ],
    );
  }

  Widget _siteBrandView() {
    final site = (_featureData['site'] as Map?)?.cast<String, dynamic>() ?? {};
    return ListView(
      children: [
        if (_featureResult != null) ...[
          ActionResultCard(
            result: _featureResult!,
            detailsBuilder: _detailValue,
            onOpenLink: _openExternal,
          ),
          const SizedBox(height: 16),
        ],
        SiteBrandPanel(
          api: _api!,
          site: site,
          pickImage: _pickImage,
          onChanged: () => _loadFeature(3),
        ),
      ],
    );
  }

  Widget _healthView() {
    final page = featurePages[3];
    final health =
        (_featureData['health'] as Map?)?.cast<String, dynamic>() ?? {};
    return ListView(
      children: [
        if (_featureResult != null) ...[
          ActionResultCard(
            result: _featureResult!,
            detailsBuilder: _detailValue,
            onOpenLink: _openExternal,
          ),
          const SizedBox(height: 16),
        ],
        HealthPanel(
          health: health,
          actions: page.actions,
          busy: _busy,
          onRunAction: _runFeatureAction,
        ),
        const SizedBox(height: 18),
        _actionList(page),
      ],
    );
  }

  Widget _socialView() {
    final page = featurePages[9];
    return ListView(
      children: [
        BufferPanel(
          api: _api!,
          workspacePath: _workspacePath,
          pickImage: _pickImage,
          onOpenSettings: () => _loadFeature(14),
          onPublished: (result) async {
            await _loadFeature(10);
            if (mounted) setState(() => _featureResult = result);
          },
        ),
        const SizedBox(height: 18),
        ..._featureChildren(page, _featureData),
      ],
    );
  }

  Widget _teamsView() {
    final page = featurePages[10];
    return ListView(
      children: [
        if (_featureResult != null) ...[
          ActionResultCard(
            result: _featureResult!,
            detailsBuilder: _detailValue,
            onOpenLink: _openExternal,
          ),
          const SizedBox(height: 16),
        ],
        TeamsPanel(
          data: _featureData,
          actions: page.actions,
          busy: _busy,
          onRunAction: _runFeatureAction,
          onOpenTeam: _openTeam,
        ),
        const SizedBox(height: 18),
        _actionList(page),
      ],
    );
  }

  Widget _settingsView() {
    final page = featurePages[13];
    final account =
        (_featureData['account'] as Map?)?.cast<String, dynamic>() ?? {};
    final ai = (_featureData['ai'] as Map?)?.cast<String, dynamic>() ?? {};
    final googleConfig =
        (_featureData['google_config'] as Map?)?.cast<String, dynamic>() ?? {};
    return ListView(
      children: [
        if (_featureResult != null) ...[
          ActionResultCard(
            result: _featureResult!,
            detailsBuilder: _detailValue,
            onOpenLink: _openExternal,
          ),
          const SizedBox(height: 16),
        ],
        SettingsPanel(
          api: _api!,
          account: account,
          ai: ai,
          googleConfig: googleConfig,
          pickImage: _pickImage,
          onChanged: () => _loadFeature(14),
        ),
        const SizedBox(height: 18),
        _actionList(page),
      ],
    );
  }

  Future<String?> _pickImage() =>
      _serviceChannel.invokeMethod<String>('chooseFile');

  void _openTeam(int teamId) {
    final api = _api;
    if (api == null) return;
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => TeamDetailView(
          api: api,
          teamId: teamId,
          actions: featurePages[10].actions,
          onRunAction: _runFeatureAction,
          onChanged: () => _loadFeature(11),
        ),
      ),
    );
  }

  void _openRequest(int requestId) {
    final api = _api;
    if (api == null) return;
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => RequestThreadView(
          api: api,
          requestId: requestId,
          workspacePath: _workspacePath,
          onChanged: () => _loadFeature(5),
        ),
      ),
    );
  }

  void _openNotificationSection(RemoteMessage message) {
    final section = message.data['section']?.toString() ?? '';
    _navigate(_sectionIndexFor(section));
  }

  int _sectionIndexFor(String section) => switch (section) {
    'dashboard' => 0,
    'studio' => 1,
    'preview' => 2,
    'site' || 'brand' => 3,
    'health' => 4,
    'requests' => 5,
    'calendar' => 6,
    'contacts' || 'inbox' => 7,
    'alerts' => 8,
    'reports' => 9,
    'social' || 'buffer' => 10,
    'teams' => 11,
    'security' => 12,
    'settings' => 14,
    'help' => 15,
    _ => 13,
  };

  List<Widget> _featureChildren(FeaturePage page, Map<String, dynamic> data) {
    final visibleData = {...data};
    if (page.title == 'Security' && data['scan_history'] is Map) {
      visibleData['scans'] = (data['scan_history'] as Map)['latest'] ?? [];
    }
    final collections = visibleData.entries
        .where((entry) => entry.value is List)
        .toList();
    return [
      Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  page.title,
                  style: const TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  page.description,
                  style: const TextStyle(color: Color(0xFF5B6B73)),
                ),
              ],
            ),
          ),
          const SizedBox(width: 20),
          OutlinedButton.icon(
            onPressed: _refreshSection,
            icon: const Icon(CupertinoIcons.arrow_clockwise, size: 17),
            label: const Text('Refresh'),
          ),
        ],
      ),
      const SizedBox(height: 18),
      if (_featureResult != null) ...[
        ActionResultCard(
          result: _featureResult!,
          detailsBuilder: _detailValue,
          onOpenLink: _openExternal,
        ),
        const SizedBox(height: 14),
      ],
      _actionList(page),
      const SizedBox(height: 18),
      if (collections.isEmpty)
        _jsonCard('Current status', data)
      else
        for (final collection in collections) ...[
          Text(
            '${_humanize(collection.key)} (${(collection.value as List).length})',
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 9),
          if ((collection.value as List).isEmpty)
            const Padding(
              padding: EdgeInsets.only(bottom: 16),
              child: Text(
                'No items yet.',
                style: TextStyle(color: _secondaryInk),
              ),
            )
          else
            ...(collection.value as List).map(
              (item) => _recordCard(page, collection.key, item),
            ),
          const SizedBox(height: 18),
        ],
    ];
  }

  String _entryTitle(dynamic value) {
    if (value is Map) {
      for (final key in [
        'title',
        'name',
        'domain',
        'email',
        'label',
        'path',
        'id',
      ]) {
        final candidate = value[key];
        if (candidate != null && candidate.toString().isNotEmpty) {
          return candidate.toString();
        }
      }
    }
    return 'Item';
  }

  String _humanize(String value) => value
      .replaceAllMapped(
        RegExp(r'([a-z])([A-Z])'),
        (match) => '${match[1]} ${match[2]}',
      )
      .replaceAll('_', ' ')
      .split(' ')
      .where((part) => part.isNotEmpty)
      .map((part) => '${part[0].toUpperCase()}${part.substring(1)}')
      .join(' ');

  Widget _recordCard(FeaturePage page, String collectionKey, dynamic value) {
    if (value is! Map) return _jsonCard('Item', value);
    final map = value.cast<String, dynamic>();
    final buttons = _recordActionButtons(page, collectionKey, map);
    final details = map.entries
        .where((entry) => !{'id', 'title', 'name', 'token'}.contains(entry.key))
        .where(
          (entry) =>
              entry.value != null &&
              entry.value is! Map &&
              entry.value is! List,
        )
        .take(4)
        .toList();
    return Padding(
      padding: const EdgeInsets.only(bottom: 9),
      child: _panel(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: const Color(0xFFF2F2F7),
                    borderRadius: BorderRadius.circular(9),
                  ),
                  child: const Icon(
                    Icons.article_outlined,
                    size: 17,
                    color: _secondaryInk,
                  ),
                ),
                const SizedBox(width: 13),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _entryTitle(value),
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: _ink,
                        ),
                      ),
                      if (details.isNotEmpty) ...[
                        const SizedBox(height: 7),
                        Wrap(
                          spacing: 14,
                          runSpacing: 5,
                          children: details
                              .map(
                                (entry) => Text(
                                  '${_humanize(entry.key)}: ${entry.value}',
                                  style: const TextStyle(
                                    fontSize: 12,
                                    color: _secondaryInk,
                                  ),
                                ),
                              )
                              .toList(),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: 10),
                IconButton(
                  tooltip: 'View details',
                  icon: const Icon(
                    Icons.chevron_right,
                    size: 18,
                    color: _secondaryInk,
                  ),
                  onPressed: () => showDialog<void>(
                    context: context,
                    builder: (context) => AlertDialog(
                      title: Text(_entryTitle(value)),
                      content: SizedBox(
                        width: 560,
                        child: SingleChildScrollView(
                          child: _detailValue(value),
                        ),
                      ),
                      actions: [
                        TextButton(
                          onPressed: () => Navigator.pop(context),
                          child: const Text('Done'),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
            if (buttons.isNotEmpty) ...[
              const SizedBox(height: 10),
              Wrap(spacing: 8, runSpacing: 8, children: buttons),
            ],
          ],
        ),
      ),
    );
  }

  List<Widget> _recordActionButtons(
    FeaturePage page,
    String collectionKey,
    Map<String, dynamic> record,
  ) {
    final buttons = <Widget>[];
    final id = record['id']?.toString() ?? '';
    final key = collectionKey.toLowerCase();
    if (page.title == 'Requests' &&
        key == 'requests' &&
        record.containsKey('status') &&
        id.isNotEmpty) {
      final requestId = int.tryParse(id);
      buttons.add(
        OutlinedButton(
          onPressed: requestId == null || _busy
              ? null
              : () => _openRequest(requestId),
          child: const Text('Open'),
        ),
      );
    }
    for (final action in page.actions) {
      if (page.title == 'Requests' && action.label == 'Open conversation') {
        continue;
      }
      final params = RegExp(
        r':([a-zA-Z_]+)',
      ).allMatches(action.path).map((match) => match.group(1)!).toList();
      if (params.isEmpty) continue;
      final overrides = <String, String>{};
      var matches = true;
      for (final param in params) {
        final base = param.endsWith('_id')
            ? param.substring(0, param.length - 3)
            : param;
        if (!key.contains(base.toLowerCase())) {
          matches = false;
          break;
        }
        final direct = record[param]?.toString() ?? '';
        final value = direct.isNotEmpty
            ? direct
            : (param.endsWith('_id') ? id : '');
        if (value.isEmpty) {
          matches = false;
          break;
        }
        overrides[param] = value;
      }
      if (!matches) continue;
      if (action.label == 'Prepare repair' &&
          record['project_linked'] != true) {
        continue;
      }
      buttons.add(
        OutlinedButton(
          onPressed: _busy
              ? null
              : () => _runFeatureAction(
                  action,
                  pathOverrides: overrides,
                  initialValues:
                      action.label.startsWith('Update ') ||
                          action.label.startsWith('Edit ')
                      ? record
                      : null,
                ),
          child: Text(action.label),
        ),
      );
    }
    return buttons;
  }

  Widget _actionList(FeaturePage page, {Set<String>? only}) {
    final visible = page.actions.where((action) => !action.coveredByPanel);
    final actions = only == null
        ? visible.toList()
        : visible.where((action) => only.contains(action.label)).toList();
    if (actions.isEmpty) return const SizedBox.shrink();
    return Wrap(
      spacing: 10,
      runSpacing: 10,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        ...actions.take(3).toList().asMap().entries.map((entry) {
        final action = entry.value;
        final icon = Icon(
          action.uploadField != null
              ? Icons.upload_file_outlined
              : _methodIcon(action.method),
          size: 16,
        );
        if (entry.key == 0) {
          return FilledButton.icon(
            onPressed: _busy ? null : () => _runFeatureAction(action),
            icon: icon,
            label: Text(action.label),
          );
        }
        return TextButton.icon(
          onPressed: _busy ? null : () => _runFeatureAction(action),
          style: TextButton.styleFrom(
            backgroundColor: Colors.white,
            foregroundColor: boardInk,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
            ),
          ),
          icon: icon,
          label: Text(action.label),
        );
      }),
      if (actions.length > 3)
        PopupMenuButton<FeatureAction>(
          tooltip: 'More actions',
          enabled: !_busy,
          onSelected: _runFeatureAction,
          itemBuilder: (context) => actions
              .skip(3)
              .map(
                (action) =>
                    PopupMenuItem(value: action, child: Text(action.label)),
              )
              .toList(),
          child: const Padding(
            padding: EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'More actions',
                  style: TextStyle(color: boardMuted, fontSize: 12),
                ),
                SizedBox(width: 8),
                Icon(Icons.more_horiz, size: 18, color: boardMuted),
              ],
            ),
          ),
        ),
      ],
    );
  }

  IconData _methodIcon(String method) => switch (method) {
    'GET' => CupertinoIcons.eye,
    'DELETE' => Icons.delete_outline_rounded,
    _ => Icons.play_arrow_rounded,
  };

  Widget _jsonCard(String title, dynamic value) => _panel(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            color: boardInk,
          ),
        ),
        const SizedBox(height: 16),
        _detailValue(value),
      ],
    ),
  );

  Widget _detailValue(dynamic value) {
    if (value is Map) {
      if (value.isEmpty) {
        return const Text(
          'Nothing here yet.',
          style: TextStyle(color: boardMuted),
        );
      }
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: value.entries.map((entry) {
          if (entry.value is Map || entry.value is List) {
            return ExpansionTile(
              tilePadding: EdgeInsets.zero,
              childrenPadding: const EdgeInsets.fromLTRB(12, 0, 0, 12),
              shape: const Border(),
              collapsedShape: const Border(),
              title: Text(
                _humanize(entry.key.toString()),
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
              children: [_detailValue(entry.value)],
            );
          }
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 9),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 150,
                  child: Text(
                    _humanize(entry.key.toString()),
                    style: const TextStyle(color: boardMuted, fontSize: 12),
                  ),
                ),
                const SizedBox(width: 18),
                Expanded(
                  child: SelectableText(
                    entry.value == null
                        ? '—'
                        : entry.value is bool
                        ? (entry.value ? 'Yes' : 'No')
                        : entry.value.toString(),
                    style: const TextStyle(
                      color: boardInk,
                      fontSize: 13,
                      height: 1.5,
                    ),
                  ),
                ),
              ],
            ),
          );
        }).toList(),
      );
    }
    if (value is List) {
      if (value.isEmpty) {
        return const Align(
          alignment: Alignment.centerLeft,
          child: Text('No items yet.', style: TextStyle(color: boardMuted)),
        );
      }
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: value
            .map(
              (item) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _detailValue(item),
              ),
            )
            .toList(),
      );
    }
    return SelectableText(
      value?.toString() ?? '—',
      style: const TextStyle(color: boardInk, fontSize: 13, height: 1.5),
    );
  }

  Widget _helpView() => ListView(
    children: [
      const Text(
        'ONEBoard Help',
        style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
      ),
      const SizedBox(height: 8),
      const Text(
        'ONEBoard brings together site management, AI content, publishing, analytics, security, and collaboration.',
        style: TextStyle(color: Color(0xFF5B6B73)),
      ),
      const SizedBox(height: 18),
      ...workspaceNavigation
          .skip(1)
          .take(14)
          .map(
            (section) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _panel(
                child: Row(
                  children: [
                    Icon(section.icon, color: cyan),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        section.title,
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
    ],
  );

  Widget _panel({required Widget child}) => BoardSurface(child: child);

  Widget _serviceUnavailableView() => Scaffold(
    body: Center(
      child: SizedBox(
        width: 460,
        child: _panel(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Center(child: BoardMark(size: 56)),
              const SizedBox(height: 13),
              Text(
                _busy ? 'Opening your workspace' : 'OneBoard could not start',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: 23,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 7),
              Text(
                _busy
                    ? 'Getting everything ready for you.'
                    : 'Please retry to reconnect to your workspace.',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Color(0xFF5B6B73)),
              ),
              const SizedBox(height: 20),
              if (_error != null) ...[
                const SizedBox(height: 12),
                SelectableText(_error!, textAlign: TextAlign.center),
              ],
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : _startService,
                child: _busy
                    ? const SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    ),
  );

  Widget _loginView() => Scaffold(
    body: BoardBackdrop(
      child: LayoutBuilder(
        builder: (context, constraints) => Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(40),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1000),
              child: Row(
                children: [
                  if (constraints.maxWidth >= 960) ...[
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.only(right: 80),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Row(
                              children: [
                                BoardMark(size: 58),
                                SizedBox(width: 17),
                                Text(
                                  'OneBoard',
                                  style: TextStyle(
                                    fontSize: 32,
                                    fontWeight: FontWeight.w700,
                                    letterSpacing: -1.4,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 46),
                            const Text(
                              'Everything that matters.\nBeautifully together.',
                              style: TextStyle(
                                fontSize: 46,
                                height: 1.12,
                                letterSpacing: -2,
                                fontWeight: FontWeight.w600,
                                color: boardInk,
                              ),
                            ),
                            const SizedBox(height: 24),
                            const Text(
                              'A thoughtful space for your websites,\nideas, and the people you create with.',
                              style: TextStyle(
                                color: boardMuted,
                                fontSize: 16,
                                height: 1.7,
                              ),
                            ),
                            const SizedBox(height: 40),
                            Wrap(
                              spacing: 12,
                              runSpacing: 12,
                              children: [
                                _authPill(CupertinoIcons.folder, 'Projects'),
                                _authPill(
                                  CupertinoIcons.sparkles,
                                  'Creativity',
                                ),
                                _authPill(
                                  Icons.people_outline_rounded,
                                  'Together',
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                  Expanded(
                    child: Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 420),
                        child: _panel(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              const Center(child: BoardMark(size: 52)),
                              const SizedBox(height: 12),
                              Text(
                                _authMode == 'register'
                                    ? 'Create your account'
                                    : _authMode == 'forgot'
                                    ? 'Reset your password'
                                    : 'Welcome back',
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                  fontSize: 26,
                                  letterSpacing: -.8,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              const SizedBox(height: 22),
                              if (_authMode == 'register') ...[
                                TextField(
                                  controller: _name,
                                  decoration: const InputDecoration(
                                    labelText: 'Name',
                                    prefixIcon: Icon(
                                      Icons.person_outline_rounded,
                                    ),
                                  ),
                                ),
                                const SizedBox(height: 12),
                              ],
                              TextField(
                                controller: _email,
                                keyboardType: TextInputType.emailAddress,
                                decoration: const InputDecoration(
                                  labelText: 'Email address',
                                  prefixIcon: Icon(Icons.mail_outline_rounded),
                                ),
                              ),
                              if (_authMode != 'forgot') ...[
                                const SizedBox(height: 12),
                                TextField(
                                  controller: _password,
                                  obscureText: true,
                                  decoration: const InputDecoration(
                                    labelText: 'Password',
                                    prefixIcon: Icon(
                                      Icons.lock_outline_rounded,
                                    ),
                                  ),
                                ),
                              ],
                              if (_authMode == 'register') ...[
                                const SizedBox(height: 12),
                                TextField(
                                  controller: _confirmPassword,
                                  obscureText: true,
                                  decoration: const InputDecoration(
                                    labelText: 'Confirm password',
                                    prefixIcon: Icon(
                                      Icons.lock_outline_rounded,
                                    ),
                                  ),
                                ),
                              ],
                              if (_authNotice != null) ...[
                                const SizedBox(height: 12),
                                _infoBanner(_authNotice!),
                              ],
                              if (_error != null) ...[
                                const SizedBox(height: 12),
                                _errorBanner(_error!),
                              ],
                              const SizedBox(height: 16),
                              FilledButton(
                                onPressed: _busy
                                    ? null
                                    : _authMode == 'register'
                                    ? _register
                                    : _authMode == 'forgot'
                                    ? _forgotPassword
                                    : _login,
                                child: _busy
                                    ? const SizedBox(
                                        height: 18,
                                        width: 18,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : Text(
                                        _authMode == 'register'
                                            ? 'Create account'
                                            : _authMode == 'forgot'
                                            ? 'Send reset link'
                                            : 'Sign in',
                                      ),
                              ),
                              Wrap(
                                alignment: WrapAlignment.center,
                                children: [
                                  if (_authMode == 'login') ...[
                                    TextButton(
                                      onPressed: () => setState(() {
                                        _authMode = 'register';
                                        _error = null;
                                        _authNotice = null;
                                      }),
                                      child: const Text('Create account'),
                                    ),
                                    TextButton(
                                      onPressed: () => setState(() {
                                        _authMode = 'forgot';
                                        _error = null;
                                        _authNotice = null;
                                      }),
                                      child: const Text('Forgot password'),
                                    ),
                                    TextButton(
                                      onPressed: _resendVerification,
                                      child: const Text('Resend verification'),
                                    ),
                                    TextButton(
                                      onPressed: _busy
                                          ? null
                                          : () => _completeEmailLink(false),
                                      child: const Text(
                                        'Verify with email link',
                                      ),
                                    ),
                                    TextButton(
                                      onPressed: _busy
                                          ? null
                                          : () => _completeEmailLink(true),
                                      child: const Text(
                                        'Reset with email link',
                                      ),
                                    ),
                                  ] else
                                    TextButton(
                                      onPressed: () => setState(() {
                                        _authMode = 'login';
                                        _error = null;
                                      }),
                                      child: const Text('Back to sign in'),
                                    ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    ),
  );

  Widget _authPill(IconData icon, String label) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
    decoration: BoxDecoration(
      color: Colors.white.withValues(alpha: .75),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 17, color: boardBlue),
        const SizedBox(width: 8),
        Text(label, style: const TextStyle(fontSize: 12, color: boardMuted)),
      ],
    ),
  );

  Widget _errorBanner(String message) => Container(
    padding: const EdgeInsets.all(11),
    decoration: BoxDecoration(
      color: const Color(0xFFB33142).withValues(alpha: .08),
      borderRadius: BorderRadius.circular(10),
    ),
    child: Text(
      message,
      style: const TextStyle(color: Color(0xFFB33142), fontSize: 12),
    ),
  );

  Widget _infoBanner(String message) => Container(
    padding: const EdgeInsets.all(11),
    decoration: BoxDecoration(
      color: cyan.withValues(alpha: .08),
      borderRadius: BorderRadius.circular(10),
    ),
    child: Text(
      message,
      style: const TextStyle(color: Color(0xFF245A9C), fontSize: 12),
    ),
  );
}
