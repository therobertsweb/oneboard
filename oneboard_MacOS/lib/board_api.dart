import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

class BoardApiException implements Exception {
  const BoardApiException(this.statusCode, this.message);
  final int statusCode;
  final String message;
  @override
  String toString() => message;
}

Map<String, dynamic> decodeApiResponse(String body, int status) {
  try {
    final decoded = body.isEmpty ? <String, dynamic>{} : jsonDecode(body);
    return decoded is Map<String, dynamic> ? decoded : {'data': decoded};
  } on FormatException {
    throw BoardApiException(
      status,
      'The ONEBoard server returned HTTP $status instead of JSON.',
    );
  }
}

class BoardApi {
  BoardApi(String address, {this.serviceToken = ''})
    : base = Uri.parse(address);
  final Uri base;
  final String serviceToken;
  final HttpClient _client = HttpClient()
    ..connectionTimeout = const Duration(seconds: 20);

  void close() => _client.close(force: true);
  final Map<String, Cookie> _cookies = {};

  String _englishPath(String path) =>
      path.contains('?') ? '$path&lang=en' : '$path?lang=en';

  Uri _resolve(String path) {
    final uri = base.resolve(_englishPath(path));
    if (uri.origin != base.origin || uri.userInfo.isNotEmpty) {
      throw ArgumentError(
        'API requests must stay on the connected ONEBoard server.',
      );
    }
    return uri;
  }

  Future<Map<String, dynamic>> get(String path) => _request('GET', path);
  Future<Map<String, dynamic>> session() =>
      _request('GET', '/api/session', allowUnauthorized: true);
  Future<Map<String, dynamic>> post(
    String path, [
    Map<String, Object?>? data,
  ]) => _request('POST', path, data: data);

  Future<Map<String, dynamic>> call(
    String method,
    String path, [
    Map<String, dynamic>? data,
  ]) => _request(method, path, data: data);

  /// Raw bytes for non-JSON endpoints (site file images, compare text files).
  Future<Uint8List> getBytes(String path) async {
    final request = await _client.getUrl(_resolve(path));
    request.followRedirects = false;
    request.headers.set(HttpHeaders.acceptHeader, '*/*');
    if (serviceToken.isNotEmpty) {
      request.headers.set('X-ONEBoard-Service-Token', serviceToken);
    }
    request.cookies.addAll(_cookies.values);
    final response = await request.close();
    for (final cookie in response.cookies) {
      _cookies[cookie.name] = cookie;
    }
    final builder = BytesBuilder(copy: false);
    await for (final chunk in response) {
      builder.add(chunk);
    }
    if (response.statusCode >= 300) {
      throw BoardApiException(
        response.statusCode,
        'HTTP error ${response.statusCode}',
      );
    }
    return builder.toBytes();
  }

  /// Session cookies (name to value) for syncing into embedded web views,
  /// which keep their own cookie store.
  Map<String, String> get sessionCookies =>
      Map.fromEntries(_cookies.values.map((c) => MapEntry(c.name, c.value)));

  Future<Map<String, dynamic>> upload(
    String path,
    String field,
    String filePath,
  ) async {
    final uri = _resolve(path);
    final request = await _client.postUrl(uri);
    final boundary = 'ONEBoard-${DateTime.now().microsecondsSinceEpoch}';
    request.followRedirects = false;
    request.headers.set(HttpHeaders.acceptHeader, 'application/json');
    request.headers.set('X-ONEBoard-Service-Token', serviceToken);
    request.headers.contentType = ContentType(
      'multipart',
      'form-data',
      parameters: {'boundary': boundary},
    );
    request.cookies.addAll(_cookies.values);
    final file = File(filePath);
    final filename = file.uri.pathSegments.last;
    final bytes = await file.readAsBytes();
    request.write(
      '--$boundary\r\nContent-Disposition: form-data; name="$field"; filename="$filename"\r\nContent-Type: application/octet-stream\r\n\r\n',
    );
    request.add(bytes);
    request.write('\r\n--$boundary--\r\n');
    final response = await request.close();
    for (final cookie in response.cookies) {
      _cookies[cookie.name] = cookie;
    }
    final body = await utf8.decoder.bind(response).join();
    final result = decodeApiResponse(body, response.statusCode);
    if (response.statusCode >= 300) {
      throw BoardApiException(
        response.statusCode,
        (result['error'] ?? 'HTTP error ${response.statusCode}').toString(),
      );
    }
    return result;
  }

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, Object?>? data,
    bool allowUnauthorized = false,
  }) async {
    final request = await _client.openUrl(method, _resolve(path));
    request.followRedirects = false;
    request.headers.set(HttpHeaders.acceptHeader, 'application/json');
    if (serviceToken.isNotEmpty) {
      request.headers.set('X-ONEBoard-Service-Token', serviceToken);
    }
    request.cookies.addAll(_cookies.values);
    if (data != null) {
      request.headers.contentType = ContentType.json;
      request.write(jsonEncode(data));
    }
    final response = await request.close();
    for (final cookie in response.cookies) {
      _cookies[cookie.name] = cookie;
    }
    final body = await utf8.decoder.bind(response).join();
    final result = decodeApiResponse(body, response.statusCode);
    if (response.statusCode >= 300 &&
        !(allowUnauthorized && response.statusCode == 401)) {
      throw BoardApiException(
        response.statusCode,
        (result['error'] ?? 'HTTP error ${response.statusCode}').toString(),
      );
    }
    return result;
  }
}
