#import <AppKit/AppKit.h>
#import <Foundation/Foundation.h>

static void Fail(NSString *message) {
    fprintf(stderr, "ERROR: %s\n", message.UTF8String);
    exit(1);
}

static NSDictionary<NSString *, NSString *> *ParseArguments(int argc, const char *argv[]) {
    NSMutableDictionary<NSString *, NSString *> *values = [NSMutableDictionary dictionary];
    for (int index = 1; index < argc; index += 2) {
        if (index + 1 >= argc) {
            Fail(@"引数の key/value ペアが壊れています。");
        }
        NSString *key = [NSString stringWithUTF8String:argv[index]];
        NSString *value = [NSString stringWithUTF8String:argv[index + 1]];
        values[key] = value;
    }
    return values;
}

static NSString *RequireArgument(NSDictionary<NSString *, NSString *> *args, NSString *key) {
    NSString *value = args[key];
    if (!value || value.length == 0) {
        Fail([NSString stringWithFormat:@"必須引数がありません: %@", key]);
    }
    return value;
}

static NSDictionary *LoadJson(NSString *path) {
    NSData *data = [NSData dataWithContentsOfFile:path];
    if (!data) {
        Fail([NSString stringWithFormat:@"spec を読めません: %@", path]);
    }
    NSError *error = nil;
    id object = [NSJSONSerialization JSONObjectWithData:data options:0 error:&error];
    if (!object || error) {
        Fail([NSString stringWithFormat:@"spec JSON の解析に失敗しました: %@", error.localizedDescription]);
    }
    if (![object isKindOfClass:[NSDictionary class]]) {
        Fail(@"spec JSON のトップレベルが object ではありません。");
    }
    return (NSDictionary *)object;
}

static double NumericValue(id value) {
    if ([value respondsToSelector:@selector(doubleValue)]) {
        return [value doubleValue];
    }
    return 0.0;
}

static NSColor *ColorFromHex(NSString *hex) {
    NSString *normalized = [[hex stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]] uppercaseString];
    if ([normalized hasPrefix:@"#"]) {
        normalized = [normalized substringFromIndex:1];
    }
    if (normalized.length != 6) {
        return [NSColor blackColor];
    }

    unsigned int rgb = 0;
    [[NSScanner scannerWithString:normalized] scanHexInt:&rgb];
    CGFloat red = ((rgb >> 16) & 0xFF) / 255.0;
    CGFloat green = ((rgb >> 8) & 0xFF) / 255.0;
    CGFloat blue = (rgb & 0xFF) / 255.0;
    return [NSColor colorWithCalibratedRed:red green:green blue:blue alpha:1.0];
}

static NSRect RectFromBox(NSDictionary *box, CGFloat canvasWidth, CGFloat canvasHeight) {
    CGFloat left = canvasWidth * (NumericValue(box[@"left_pct"]) / 100.0);
    CGFloat top = canvasHeight * (NumericValue(box[@"top_pct"]) / 100.0);
    CGFloat width = canvasWidth * (NumericValue(box[@"width_pct"]) / 100.0);
    CGFloat height = canvasHeight * (NumericValue(box[@"height_pct"]) / 100.0);
    CGFloat originY = canvasHeight - top - height;
    return NSMakeRect(left, originY, width, height);
}

static NSFont *FontFromSpec(NSDictionary *style) {
    CGFloat size = NumericValue(style[@"font_size_pt"]);
    if (size <= 0.0) {
        size = 10.0;
    }

    NSString *fontName = style[@"font_name"];
    if (fontName.length > 0) {
        NSFont *font = [NSFont fontWithName:fontName size:size];
        if (font) {
            return font;
        }
    }
    return [NSFont systemFontOfSize:size];
}

static NSTextAlignment TextAlignmentFromSpec(NSString *alignment) {
    if ([alignment isEqualToString:@"right"]) {
        return NSTextAlignmentRight;
    }
    if ([alignment isEqualToString:@"center"]) {
        return NSTextAlignmentCenter;
    }
    return NSTextAlignmentLeft;
}

static void DrawText(NSString *text, NSDictionary *style, NSDictionary *box, CGFloat canvasWidth, CGFloat canvasHeight) {
    if (!text || text.length == 0) {
        return;
    }

    NSMutableParagraphStyle *paragraphStyle = [[NSMutableParagraphStyle alloc] init];
    paragraphStyle.alignment = TextAlignmentFromSpec(style[@"alignment"]);
    paragraphStyle.lineBreakMode = NSLineBreakByTruncatingTail;

    NSDictionary *attributes = @{
        NSFontAttributeName: FontFromSpec(style),
        NSForegroundColorAttributeName: ColorFromHex(style[@"color_hex"] ?: @"000000"),
        NSParagraphStyleAttributeName: paragraphStyle,
    };

    NSRect rect = RectFromBox(box, canvasWidth, canvasHeight);
    [text drawInRect:rect withAttributes:attributes];
}

static void DrawImageAsset(NSString *assetPath, NSDictionary *box, CGFloat canvasWidth, CGFloat canvasHeight) {
    NSImage *image = [[NSImage alloc] initWithContentsOfFile:assetPath];
    if (!image) {
        Fail([NSString stringWithFormat:@"画像アセットを読めません: %@", assetPath]);
    }
    NSRect rect = RectFromBox(box, canvasWidth, canvasHeight);
    [image drawInRect:rect];
}

static NSBitmapImageRep *BitmapRepFromPath(NSString *path) {
    NSData *data = [NSData dataWithContentsOfFile:path];
    if (!data) {
        Fail([NSString stringWithFormat:@"入力画像を読めません: %@", path]);
    }
    NSBitmapImageRep *rep = [NSBitmapImageRep imageRepWithData:data];
    if (!rep) {
        Fail([NSString stringWithFormat:@"入力画像を画像として解釈できません: %@", path]);
    }
    return rep;
}

static NSString *PageNumberString(NSDictionary *spec, NSInteger page, NSInteger total, NSString *overrideFormat) {
    NSDictionary *defaults = spec[@"render_defaults"];
    NSString *format = overrideFormat.length > 0 ? overrideFormat : defaults[@"page_number_format"];
    if (format.length == 0) {
        format = @"number-only";
    }

    NSInteger minDigits = MAX(1, (NSInteger)NumericValue(defaults[@"page_number_min_digits"]));
    NSInteger dynamicDigits = MAX((NSInteger)[@(total) stringValue].length, minDigits);
    NSString *pageString = [NSString stringWithFormat:@"%0*ld", (int)dynamicDigits, (long)page];
    NSString *totalString = [NSString stringWithFormat:@"%0*ld", (int)dynamicDigits, (long)total];

    if ([format isEqualToString:@"current-total"]) {
        return [NSString stringWithFormat:@"%ld / %ld", (long)page, (long)total];
    }
    if ([format isEqualToString:@"zero-padded-total"]) {
        return [NSString stringWithFormat:@"%@ / %@", pageString, totalString];
    }
    if ([format isEqualToString:@"zero-padded"]) {
        return pageString;
    }
    return [NSString stringWithFormat:@"%ld", (long)page];
}

static void EnsureParentDirectory(NSString *outputPath) {
    NSString *directory = [outputPath stringByDeletingLastPathComponent];
    NSError *error = nil;
    if (![[NSFileManager defaultManager] createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:&error]) {
        Fail([NSString stringWithFormat:@"出力ディレクトリを作れません: %@", error.localizedDescription]);
    }
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSDictionary<NSString *, NSString *> *args = ParseArguments(argc, argv);
        NSString *mode = RequireArgument(args, @"--mode");
        NSString *specPath = RequireArgument(args, @"--spec");
        NSString *variant = RequireArgument(args, @"--variant");
        NSString *outputPath = RequireArgument(args, @"--output");

        NSDictionary *spec = LoadJson(specPath);
        NSDictionary *variants = spec[@"variants"];
        NSDictionary *variantSpec = variants[variant];
        if (!variantSpec) {
            Fail([NSString stringWithFormat:@"未知の frame variant です: %@", variant]);
        }

        CGFloat canvasWidth = 0.0;
        CGFloat canvasHeight = 0.0;
        NSBitmapImageRep *baseRep = nil;
        NSString *inputPath = args[@"--input"];
        if (inputPath.length > 0) {
            baseRep = BitmapRepFromPath(inputPath);
            canvasWidth = (CGFloat)baseRep.pixelsWide;
            canvasHeight = (CGFloat)baseRep.pixelsHigh;
        } else {
            NSDictionary *defaults = spec[@"render_defaults"];
            canvasWidth = NumericValue(defaults[@"canvas_width_px"]);
            canvasHeight = NumericValue(defaults[@"canvas_height_px"]);
            if (canvasWidth <= 0.0 || canvasHeight <= 0.0) {
                Fail(@"frame only 出力には render_defaults.canvas_width_px / canvas_height_px が必要です。");
            }
        }

        NSBitmapImageRep *outputRep = [[NSBitmapImageRep alloc]
            initWithBitmapDataPlanes:NULL
                          pixelsWide:(NSInteger)canvasWidth
                          pixelsHigh:(NSInteger)canvasHeight
                       bitsPerSample:8
                     samplesPerPixel:4
                            hasAlpha:YES
                            isPlanar:NO
                      colorSpaceName:NSCalibratedRGBColorSpace
                         bytesPerRow:0
                        bitsPerPixel:0];
        NSGraphicsContext *context = [NSGraphicsContext graphicsContextWithBitmapImageRep:outputRep];
        [NSGraphicsContext saveGraphicsState];
        [NSGraphicsContext setCurrentContext:context];
        context.imageInterpolation = NSImageInterpolationHigh;

        [[NSColor clearColor] setFill];
        NSRectFill(NSMakeRect(0.0, 0.0, canvasWidth, canvasHeight));

        if (baseRep) {
            NSImage *baseImage = [[NSImage alloc] initWithSize:NSMakeSize(canvasWidth, canvasHeight)];
            [baseImage addRepresentation:baseRep];
            [baseImage drawInRect:NSMakeRect(0.0, 0.0, canvasWidth, canvasHeight)];
        }

        NSString *specDirectory = [specPath stringByDeletingLastPathComponent];
        for (NSDictionary *imageSpec in variantSpec[@"images"]) {
            NSString *assetFilename = imageSpec[@"asset"];
            NSString *assetPath = [specDirectory stringByAppendingPathComponent:assetFilename];
            DrawImageAsset(assetPath, imageSpec[@"box_pct"], canvasWidth, canvasHeight);
        }

        NSDictionary *footerSpec = spec[@"footer"];
        DrawText(footerSpec[@"text"], footerSpec, footerSpec[@"box_pct"], canvasWidth, canvasHeight);

        NSString *pageArgument = args[@"--page"];
        NSString *totalArgument = args[@"--total"];
        if (pageArgument.length > 0 && totalArgument.length > 0) {
            NSInteger page = pageArgument.integerValue;
            NSInteger total = totalArgument.integerValue;
            if (page > 0 && total > 0) {
                NSDictionary *pageSpec = spec[@"page_number"];
                NSString *pageText = PageNumberString(spec, page, total, args[@"--page-format"]);
                DrawText(pageText, pageSpec, pageSpec[@"box_pct"], canvasWidth, canvasHeight);
            }
        }

        [NSGraphicsContext restoreGraphicsState];

        NSData *pngData = [outputRep representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
        if (!pngData) {
            Fail(@"PNG への書き出しに失敗しました。");
        }

        EnsureParentDirectory(outputPath);
        if (![pngData writeToFile:outputPath atomically:YES]) {
            Fail([NSString stringWithFormat:@"出力ファイルを書き出せません: %@", outputPath]);
        }

        if ([mode isEqualToString:@"frame"] || [mode isEqualToString:@"composite"]) {
            return 0;
        }
        Fail([NSString stringWithFormat:@"未知の mode です: %@", mode]);
    }
    return 0;
}
