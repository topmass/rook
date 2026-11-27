#import <ApplicationServices/ApplicationServices.h>
#import <AVFoundation/AVFoundation.h>
#import <Cocoa/Cocoa.h>
#import <CoreGraphics/CoreGraphics.h>
#import <WebKit/WebKit.h>
#include <errno.h>
#include <signal.h>
#include <spawn.h>
#include <sys/wait.h>

extern char **environ;

// A press of Right Option becomes a talk only after it stays alone this long, or on a clean release.
static const double kTalkKeySettle = 0.15;

static void emitJSON(NSDictionary *payload) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:payload options:0 error:nil];
    if (!data) return;
    NSMutableData *line = [data mutableCopy];
    [line appendBytes:"\n" length:1];
    [[NSFileHandle fileHandleWithStandardOutput] writeData:line];
}

// Pure state machine for the macOS talk key (default Right Option, keyCode 61) with the chord rule.
// European layouts type @ and accents with Option, so a press stays pending: it sends "down" only after
// kTalkKeySettle seconds alone (tick:) or on a clean release. Any other key or modifier while pending
// drops the press with no event. A chord after "down" sends chord_cancel, as before.
@interface TalkKeyMachine : NSObject
@property (nonatomic, readonly) int64_t targetKeyCode;
@property (nonatomic, readonly) BOOL held;
@property (nonatomic, readonly) BOOL chorded;
@property (nonatomic, readonly) BOOL pending;
@property (nonatomic, readonly) double downAt;
- (instancetype)initWithKeyCode:(int64_t)keyCode;
- (NSArray<NSDictionary *> *)handleFlagsChanged:(int64_t)keyCode
                                  alternateDown:(BOOL)alternateDown
                             otherModifiersDown:(BOOL)otherMods
                                             ts:(double)ts;
- (NSArray<NSDictionary *> *)handleKeyDown:(int64_t)keyCode ts:(double)ts;
- (NSArray<NSDictionary *> *)tick:(double)ts;
@end

@implementation TalkKeyMachine

- (instancetype)initWithKeyCode:(int64_t)keyCode {
    if ((self = [super init])) {
        _targetKeyCode = keyCode;
        _held = NO;
        _chorded = NO;
        _pending = NO;
        _downAt = 0.0;
    }
    return self;
}

- (NSDictionary *)downEvent {
    return @{@"type": @"talk_key", @"action": @"down", @"key": @"RightOption", @"ts": @(_downAt)};
}

- (NSArray<NSDictionary *> *)chord:(double)ts {
    if (!_held || _chorded) return @[];
    _chorded = YES;
    if (_pending) {
        _pending = NO;  // Typing, not talking: the press never becomes a talk.
        return @[];
    }
    return @[@{@"type": @"talk_key", @"action": @"chord_cancel", @"key": @"RightOption", @"ts": @(ts)}];
}

- (NSArray<NSDictionary *> *)handleFlagsChanged:(int64_t)keyCode
                                  alternateDown:(BOOL)alternateDown
                             otherModifiersDown:(BOOL)otherMods
                                             ts:(double)ts {
    if (keyCode == _targetKeyCode) {
        if (alternateDown && !_held) {
            if (otherMods) return @[];
            _held = YES;
            _chorded = NO;
            _pending = YES;
            _downAt = ts;
            return @[];
        }
        if (!alternateDown && _held) {
            BOOL wasChorded = _chorded, wasPending = _pending;
            double elapsed = MAX(0.0, ts - _downAt);
            _held = NO;
            _chorded = NO;
            _pending = NO;
            if (wasChorded) return @[];
            NSDictionary *up = @{@"type": @"talk_key", @"action": @"up", @"key": @"RightOption",
                                 @"held": @(elapsed), @"ts": @(ts)};
            return wasPending ? @[[self downEvent], up] : @[up];
        }
        return @[];
    }
    return [self chord:ts];
}

- (NSArray<NSDictionary *> *)handleKeyDown:(int64_t)keyCode ts:(double)ts {
    return keyCode == _targetKeyCode ? @[] : [self chord:ts];
}

- (NSArray<NSDictionary *> *)tick:(double)ts {
    // A stale tick from an earlier press is too early for this one, so it sends nothing.
    if (!_held || !_pending || ts - _downAt < kTalkKeySettle - 0.01) return @[];
    _pending = NO;
    return @[[self downEvent]];
}

@end

// Stand-in event source mode: tests TalkKeyMachine from stdin JSON lines with zero CoreGraphics or AppKit calls.
static int runKeyTestMode(void) {
    TalkKeyMachine *machine = [[TalkKeyMachine alloc] initWithKeyCode:61];
    char buf[4096];
    while (fgets(buf, sizeof(buf), stdin) != NULL) {
        NSString *line = [[NSString stringWithUTF8String:buf]
                          stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
        if (line.length == 0) continue;
        NSData *data = [line dataUsingEncoding:NSUTF8StringEncoding];
        id obj = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
        if (![obj isKindOfClass:[NSDictionary class]]) continue;
        NSDictionary *dict = (NSDictionary *)obj;
        NSString *event = [dict[@"event"] isKindOfClass:[NSString class]] ? dict[@"event"] : @"";
        int64_t keyCode = [dict[@"keyCode"] respondsToSelector:@selector(longLongValue)]
            ? [dict[@"keyCode"] longLongValue] : 0;
        double ts = [dict[@"ts"] respondsToSelector:@selector(doubleValue)]
            ? [dict[@"ts"] doubleValue] : 0.0;
        NSArray<NSDictionary *> *out = @[];
        if ([event isEqualToString:@"flags"]) {
            BOOL alt = [dict[@"alternate"] respondsToSelector:@selector(boolValue)]
                ? [dict[@"alternate"] boolValue] : NO;
            BOOL other = [dict[@"otherModifiers"] respondsToSelector:@selector(boolValue)]
                ? [dict[@"otherModifiers"] boolValue] : NO;
            out = [machine handleFlagsChanged:keyCode alternateDown:alt otherModifiersDown:other ts:ts];
        } else if ([event isEqualToString:@"keyDown"]) {
            out = [machine handleKeyDown:keyCode ts:ts];
        } else if ([event isEqualToString:@"tick"]) {
            out = [machine tick:ts];
        }
        for (NSDictionary *item in out) {
            emitJSON(item);
        }
    }
    return 0;
}

@interface EventTapHost : NSObject
@property (nonatomic, strong) TalkKeyMachine *machine;
- (BOOL)startIfAuthorized;
@end

static CGEventRef eventTapCallback(CGEventTapProxy proxy, CGEventType type, CGEventRef event, void *userInfo) {
    (void)proxy;
    if (!userInfo) return event;
    EventTapHost *host = (__bridge EventTapHost *)userInfo;
    int64_t keyCode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode);
    double ts = [[NSProcessInfo processInfo] systemUptime];
    NSArray<NSDictionary *> *emitted = @[];
    if (type == kCGEventFlagsChanged) {
        CGEventFlags flags = CGEventGetFlags(event);
        BOOL altDown = (flags & kCGEventFlagMaskAlternate) != 0;
        BOOL otherMods = (flags & (kCGEventFlagMaskCommand | kCGEventFlagMaskControl | kCGEventFlagMaskShift)) != 0;
        emitted = [host.machine handleFlagsChanged:keyCode alternateDown:altDown otherModifiersDown:otherMods ts:ts];
    } else if (type == kCGEventKeyDown) {
        emitted = [host.machine handleKeyDown:keyCode ts:ts];
    }
    for (NSDictionary *item in emitted) {
        emitJSON(item);
    }
    if (type == kCGEventFlagsChanged && host.machine.pending && keyCode == host.machine.targetKeyCode) {
        __weak EventTapHost *weakHost = host;
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(kTalkKeySettle * NSEC_PER_SEC)),
                       dispatch_get_main_queue(), ^{
            for (NSDictionary *item in [weakHost.machine tick:[[NSProcessInfo processInfo] systemUptime]]) {
                emitJSON(item);
            }
        });
    }
    return event;
}

@implementation EventTapHost {
    CFMachPortRef _tap;
    CFRunLoopSourceRef _source;
}

- (instancetype)init {
    if ((self = [super init])) {
        _machine = [[TalkKeyMachine alloc] initWithKeyCode:61];
    }
    return self;
}

- (BOOL)startIfAuthorized {
    // Read-only preflight check; never opens a permission dialog.
    if (!CGPreflightListenEventAccess()) {
        emitJSON(@{@"type": @"keys_unavailable",
                   @"reason": @"Input Monitoring permission is not granted for Rook.app."});
        return NO;
    }
    CGEventMask mask = CGEventMaskBit(kCGEventFlagsChanged) | CGEventMaskBit(kCGEventKeyDown);
    _tap = CGEventTapCreate(kCGSessionEventTap, kCGHeadInsertEventTap, kCGEventTapOptionListenOnly,
                            mask, eventTapCallback, (__bridge void *)self);
    if (!_tap) {
        emitJSON(@{@"type": @"keys_unavailable", @"reason": @"Could not create listen-only event tap."});
        return NO;
    }
    _source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, _tap, 0);
    CFRunLoopAddSource(CFRunLoopGetMain(), _source, kCFRunLoopCommonModes);
    CGEventTapEnable(_tap, true);
    emitJSON(@{@"type": @"keys_ready", @"key": @"RightOption"});
    return YES;
}

- (void)dealloc {
    if (_source) CFRelease(_source);
    if (_tap) CFRelease(_tap);
}

@end

@interface PresencePanel : NSPanel
@end

@implementation PresencePanel
- (BOOL)canBecomeKeyWindow { return NO; }
- (BOOL)canBecomeMainWindow { return NO; }
@end

@interface AppDelegate : NSObject <NSApplicationDelegate, WKNavigationDelegate>
@property (nonatomic, copy) NSString *urlString;
@property (nonatomic, assign) CGFloat width;
@property (nonatomic, assign) CGFloat height;
@property (nonatomic, assign) BOOL enableKeys;
@property (nonatomic, strong) NSNumber *smokeSeconds;
@property (nonatomic, copy) NSString *token;
@property (nonatomic, strong) PresencePanel *panel;
@property (nonatomic, strong) WKWebView *webView;
@property (nonatomic, strong) EventTapHost *eventTap;
@property (nonatomic, assign) BOOL finishedLoad;
@property (nonatomic, copy) NSString *allowedScheme;
@property (nonatomic, copy) NSString *allowedHost;
@property (nonatomic, strong) NSNumber *allowedPort;
@end

static BOOL isLoopbackURL(NSURL *url) {
    if (!url) return NO;
    NSString *scheme = url.scheme.lowercaseString;
    NSString *host = url.host.lowercaseString;
    if (!([scheme isEqualToString:@"http"] || [scheme isEqualToString:@"https"])) return NO;
    return [host isEqualToString:@"127.0.0.1"] || [host isEqualToString:@"localhost"];
}

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    (void)notification;
    [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];

    NSRect screenFrame = NSScreen.mainScreen ? NSScreen.mainScreen.visibleFrame : NSMakeRect(0, 0, 1280, 800);
    NSRect fullFrame = NSScreen.mainScreen ? NSScreen.mainScreen.frame : screenFrame;
    // Top centre of the screen, as Rook sits on Linux: the middle of the whole screen, so a side Dock does not
    // push it off-centre, and below the menu bar. Whole points, so the panel stays sharp on a 1x screen.
    NSRect frame = NSMakeRect(round(NSMidX(fullFrame) - self.width / 2),
                              round(NSMaxY(screenFrame) - self.height - 24),
                              self.width, self.height);

    PresencePanel *panel = [[PresencePanel alloc]
                            initWithContentRect:frame
                            styleMask:(NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel)
                            backing:NSBackingStoreBuffered
                            defer:NO];
    panel.level = NSFloatingWindowLevel;
    panel.opaque = NO;
    panel.backgroundColor = [NSColor clearColor];
    panel.hasShadow = NO;
    panel.ignoresMouseEvents = YES;
    panel.hidesOnDeactivate = NO;
    panel.collectionBehavior = (NSWindowCollectionBehaviorCanJoinAllSpaces
                                | NSWindowCollectionBehaviorFullScreenAuxiliary
                                | NSWindowCollectionBehaviorStationary
                                | NSWindowCollectionBehaviorIgnoresCycle);

    WKWebViewConfiguration *config = [[WKWebViewConfiguration alloc] init];
    config.websiteDataStore = [WKWebsiteDataStore nonPersistentDataStore];
    WKWebView *webView = [[WKWebView alloc] initWithFrame:NSMakeRect(0, 0, frame.size.width, frame.size.height)
                                            configuration:config];
    webView.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    webView.navigationDelegate = self;
    [webView setValue:@NO forKey:@"drawsBackground"];

    panel.contentView = webView;
    [panel orderFrontRegardless];
    self.panel = panel;
    self.webView = webView;

    [self loadPresenceInto:webView];

    if (self.enableKeys) {
        EventTapHost *tap = [[EventTapHost alloc] init];
        [tap startIfAuthorized];
        self.eventTap = tap;
    }

    [self startStdinReader];

    if (self.smokeSeconds != nil) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(self.smokeSeconds.doubleValue * NSEC_PER_SEC)),
                       dispatch_get_main_queue(), ^{
            [self emitSmokeAndExit];
        });
    }
}

- (void)loadPresenceInto:(WKWebView *)webView {
    NSURL *url = [NSURL URLWithString:self.urlString];
    if (!isLoopbackURL(url)) {
        emitJSON(@{@"type": @"error", @"error": [NSString stringWithFormat:@"Refusing non-loopback URL: %@", self.urlString]});
        dispatch_async(dispatch_get_main_queue(), ^{ [NSApp terminate:nil]; });
        return;
    }
    self.allowedScheme = url.scheme.lowercaseString;
    self.allowedHost = url.host.lowercaseString;
    self.allowedPort = url.port;
    NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:url];
    if (self.token.length > 0) {
        [req setValue:self.token forHTTPHeaderField:@"X-Rook-Presence-Token"];
    }
    [webView loadRequest:req];
}

- (void)webView:(WKWebView *)webView
decidePolicyForNavigationAction:(WKNavigationAction *)navigationAction
decisionHandler:(void (^)(WKNavigationActionPolicy))decisionHandler {
    (void)webView;
    NSURL *target = navigationAction.request.URL;
    BOOL samePort = ((self.allowedPort == nil && target.port == nil)
                     || (self.allowedPort != nil && [self.allowedPort isEqualToNumber:target.port]));
    BOOL sameOrigin = (target != nil
                       && self.allowedScheme != nil
                       && self.allowedHost != nil
                       && [target.scheme.lowercaseString isEqualToString:self.allowedScheme]
                       && [target.host.lowercaseString isEqualToString:self.allowedHost]
                       && samePort);
    if (!sameOrigin) {
        emitJSON(@{@"type": @"blocked_navigation", @"url": target.absoluteString ?: @""});
        decisionHandler(WKNavigationActionPolicyCancel);
        return;
    }
    decisionHandler(WKNavigationActionPolicyAllow);
}

- (void)webView:(WKWebView *)webView didFinishNavigation:(WKNavigation *)navigation {
    (void)navigation;
    self.finishedLoad = YES;
    emitJSON(@{
        @"type": @"ready",
        @"url": webView.URL.absoluteString ?: self.urlString,
        @"active": @(NSApp.isActive),
        @"ignoresMouseEvents": @(self.panel.ignoresMouseEvents),
        @"isOpaque": @(self.panel.isOpaque),
    });
}

- (void)webView:(WKWebView *)webView didFailNavigation:(WKNavigation *)navigation withError:(NSError *)error {
    (void)webView; (void)navigation;
    emitJSON(@{@"type": @"error", @"error": error.localizedDescription ?: @"Navigation failed"});
}

- (void)webView:(WKWebView *)webView didFailProvisionalNavigation:(WKNavigation *)navigation withError:(NSError *)error {
    (void)webView; (void)navigation;
    emitJSON(@{@"type": @"error", @"error": error.localizedDescription ?: @"Provisional navigation failed"});
}

- (void)emitSmokeAndExit {
    BOOL active = NSApp.isActive;
    BOOL ignores = self.panel.ignoresMouseEvents;
    BOOL opaque = self.panel.isOpaque;
    void (^finish)(NSDictionary *) = ^(NSDictionary *hostInfo) {
        emitJSON(@{
            @"type": @"smoke",
            @"loaded": @(self.finishedLoad),
            @"active": @(active),
            @"ignoresMouseEvents": @(ignores),
            @"isOpaque": @(opaque),
            @"host": hostInfo ?: @{},
        });
        [NSApp terminate:nil];
    };
    if (!self.webView) {
        finish(@{});
        return;
    }
    [self.webView evaluateJavaScript:@"window.rookPresenceHost ? window.rookPresenceHost.info() : {}"
                   completionHandler:^(id result, NSError *error) {
        (void)error;
        finish([result isKindOfClass:[NSDictionary class]] ? (NSDictionary *)result : @{});
    }];
}

- (void)startStdinReader {
    __weak typeof(self) weakSelf = self;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        char buf[4096];
        while (fgets(buf, sizeof(buf), stdin) != NULL) {
            NSString *line = [[NSString stringWithUTF8String:buf]
                              stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
            if (line.length == 0) continue;
            NSData *data = [line dataUsingEncoding:NSUTF8StringEncoding];
            id obj = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
            if (![obj isKindOfClass:[NSDictionary class]]) continue;
            NSDictionary *dict = (NSDictionary *)obj;
            if ([dict[@"quit"] respondsToSelector:@selector(boolValue)] && [dict[@"quit"] boolValue]) {
                dispatch_async(dispatch_get_main_queue(), ^{ [NSApp terminate:nil]; });
                return;
            }
            NSString *kind = [dict[@"event"] isKindOfClass:[NSString class]] ? dict[@"event"] : @"state";
            NSData *kindData = [NSJSONSerialization dataWithJSONObject:@[kind] options:0 error:nil];
            NSData *jsonData = [NSJSONSerialization dataWithJSONObject:dict options:0 error:nil];
            if (!kindData || !jsonData) continue;
            NSString *kindArr = [[NSString alloc] initWithData:kindData encoding:NSUTF8StringEncoding];
            NSString *jsonStr = [[NSString alloc] initWithData:jsonData encoding:NSUTF8StringEncoding];
            dispatch_async(dispatch_get_main_queue(), ^{
                NSString *js = [NSString stringWithFormat:
                    @"window.rookPresenceHost && window.rookPresenceHost.apply((%@)[0], %@);", kindArr, jsonStr];
                [weakSelf.webView evaluateJavaScript:js completionHandler:nil];
            });
        }
        if (weakSelf.smokeSeconds == nil) {
            dispatch_async(dispatch_get_main_queue(), ^{ [NSApp terminate:nil]; });
        }
    });
}

@end

// Launcher mode: launchd runs Rook.app, and Rook.app runs Rook's Python as its child. macOS charges each
// permission to the responsible process, so every grant belongs to this signed bundle, not to Python.
static volatile pid_t gChild = 0;

static void forwardSignal(int sig) {
    pid_t child = gChild;
    if (child > 0) kill(child, sig);
}

static int runLauncher(int argc, const char *argv[], int first) {
    if (first >= argc) {
        fprintf(stderr, "Usage: RookHelper --launch PROGRAM [ARGS...]\n");
        return 2;
    }
    NSString *me = NSBundle.mainBundle.executablePath;
    if (me) setenv("ROOK_MAC_HELPER", me.fileSystemRepresentation, 1);
    struct sigaction sa = {0};
    sa.sa_handler = forwardSignal;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGHUP, &sa, NULL);
    pid_t pid = 0;
    int err = posix_spawn(&pid, argv[first], NULL, NULL, (char *const *)&argv[first], environ);
    if (err) {
        fprintf(stderr, "Rook.app could not start %s: %s\n", argv[first], strerror(err));
        return 127;
    }
    gChild = pid;
    int status = 0;
    while (waitpid(pid, &status, 0) < 0) {
        if (errno != EINTR) return 1;
    }
    if (WIFEXITED(status)) return WEXITSTATUS(status);  // A clean stop exits 0, so launchd leaves Rook down.
    return WIFSIGNALED(status) ? 128 + WTERMSIG(status) : 1;
}

// Opened by Finder or by System Settings' "Quit & Reopen": restart Rook through launchd, never a second Rook.
static int kickLaunchd(void) {
    NSString *label = NSProcessInfo.processInfo.environment[@"ROOK_LAUNCHD_LABEL"] ?: @"com.rook.companion";
    NSString *target = [NSString stringWithFormat:@"gui/%u/%@", getuid(), label];
    const char *args[] = {"/bin/launchctl", "kickstart", "-k", target.UTF8String, NULL};
    pid_t pid = 0;
    if (posix_spawn(&pid, args[0], NULL, NULL, (char *const *)args, environ) != 0) return 1;
    int status = 0;
    while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {}
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}

// Read each permission without a prompt. Run from Rook (or under the launcher), the answer is Rook.app's.
static int runCheckAccess(void) {
    NSString *mic = @"not asked";
    switch ([AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio]) {
        case AVAuthorizationStatusAuthorized: mic = @"allowed"; break;
        case AVAuthorizationStatusDenied: mic = @"denied"; break;
        case AVAuthorizationStatusRestricted: mic = @"restricted"; break;
        default: break;
    }
    emitJSON(@{@"type": @"access", @"microphone": mic, @"input": @(CGPreflightListenEventAccess()),
               @"screen": @(CGPreflightScreenCaptureAccess()), @"accessibility": AXIsProcessTrusted() ? @YES : @NO});
    return 0;
}

// Show Apple's own prompt for one permission, which also adds Rook to its list in System Settings.
static int runRequestAccess(NSString *grant) {
    if ([grant isEqualToString:@"microphone"]) {
        dispatch_semaphore_t answered = dispatch_semaphore_create(0);
        [AVCaptureDevice requestAccessForMediaType:AVMediaTypeAudio completionHandler:^(BOOL granted) {
            (void)granted;
            dispatch_semaphore_signal(answered);
        }];
        dispatch_semaphore_wait(answered, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(120 * NSEC_PER_SEC)));
    } else if ([grant isEqualToString:@"input"]) {
        CGRequestListenEventAccess();
    } else if ([grant isEqualToString:@"screen"]) {
        CGRequestScreenCaptureAccess();
    } else if ([grant isEqualToString:@"accessibility"]) {
        AXIsProcessTrustedWithOptions((__bridge CFDictionaryRef)@{(__bridge NSString *)kAXTrustedCheckOptionPrompt: @YES});
    } else {
        fprintf(stderr, "Usage: RookHelper --request-access microphone|input|screen|accessibility\n");
        return 2;
    }
    return runCheckAccess();
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc == 1 || (argc == 2 && strncmp(argv[1], "-psn_", 5) == 0)) {
            return kickLaunchd();
        }
        if (strcmp(argv[1], "--launch") == 0) {
            return runLauncher(argc, argv, 2);
        }
        if (strcmp(argv[1], "--check-access") == 0) {
            return runCheckAccess();
        }
        if (strcmp(argv[1], "--request-access") == 0) {
            return runRequestAccess(argc > 2 ? [NSString stringWithUTF8String:argv[2]] : @"");
        }
        NSString *url = @"http://127.0.0.1:47326/presence";
        CGFloat width = 220.0;
        CGFloat height = 220.0;
        BOOL enableKeys = NO;
        BOOL testKeys = NO;
        NSNumber *smokeSeconds = nil;

        for (int i = 1; i < argc; i++) {
            NSString *arg = [NSString stringWithUTF8String:argv[i]];
            if ([arg isEqualToString:@"--url"] && i + 1 < argc) {
                url = [NSString stringWithUTF8String:argv[++i]];
            } else if ([arg isEqualToString:@"--width"] && i + 1 < argc) {
                width = atof(argv[++i]);
            } else if ([arg isEqualToString:@"--height"] && i + 1 < argc) {
                height = atof(argv[++i]);
            } else if ([arg isEqualToString:@"--enable-keys"]) {
                enableKeys = YES;
            } else if ([arg isEqualToString:@"--test-keys"]) {
                testKeys = YES;
            } else if ([arg isEqualToString:@"--smoke-seconds"] && i + 1 < argc) {
                smokeSeconds = @(atof(argv[++i]));
            }
        }

        if (testKeys) {
            return runKeyTestMode();
        }

        [NSApplication sharedApplication];
        AppDelegate *delegate = [[AppDelegate alloc] init];
        delegate.urlString = url;
        delegate.width = width;
        delegate.height = height;
        delegate.enableKeys = enableKeys;
        delegate.smokeSeconds = smokeSeconds;
        delegate.token = NSProcessInfo.processInfo.environment[@"ROOK_PRESENCE_TOKEN"];
        NSApp.delegate = delegate;
        [NSApp run];
    }
    return 0;
}
