"""
Converts MiniFASNet V2 weights (.pth) to ONNX format.
Architecture is inferred automatically from the weight shapes.

Requirements: pip install torch --index-url https://download.pytorch.org/whl/cpu
Run once:    python setup_liveness.py
"""
import os
import sys


def main():
    print("MiniFASNet V2 -> ONNX Conversion")
    print("=" * 40)

    src = 'Silent-Face-Anti-Spoofing/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth'
    dst = 'models/2.7_80x80_MiniFASNetV2.onnx'

    if not os.path.exists(src):
        print(f"ERROR: Source model not found: {src}")
        sys.exit(1)

    if os.path.exists(dst):
        print(f"ONNX model already exists: {dst}")
        sys.exit(0)

    try:
        import torch
        import torch.nn as nn
    except ImportError:
        print("Install PyTorch first:")
        print("  pip install torch --index-url https://download.pytorch.org/whl/cpu")
        sys.exit(1)

    print(f"Loading weights from: {src}")
    checkpoint = torch.load(src, map_location='cpu')
    sd = checkpoint.get('state_dict', checkpoint)
    sd = {k.replace('module.', ''): v for k, v in sd.items()}
    print(f"Weight tensors: {len(sd)}")

    # ---- Build model from actual weight shapes ----

    class Conv_block(nn.Module):
        def __init__(self, in_c, out_c, kernel=(1,1), stride=(1,1), padding=(0,0), groups=1):
            super().__init__()
            self.conv = nn.Conv2d(in_c, out_c, kernel, stride, padding, groups=groups, bias=False)
            self.bn   = nn.BatchNorm2d(out_c)
            self.prelu = nn.PReLU(out_c)
        def forward(self, x):
            return self.prelu(self.bn(self.conv(x)))

    class Linear_block(nn.Module):
        def __init__(self, in_c, out_c, kernel=(1,1), stride=(1,1), padding=(0,0), groups=1):
            super().__init__()
            self.conv = nn.Conv2d(in_c, out_c, kernel, stride, padding, groups=groups, bias=False)
            self.bn   = nn.BatchNorm2d(out_c)
        def forward(self, x):
            return self.bn(self.conv(x))

    class Depth_Wise(nn.Module):
        def __init__(self, in_c, mid_c, out_c, stride=(2,2), residual=False):
            super().__init__()
            self.conv     = Conv_block(in_c, mid_c, kernel=(1,1), stride=(1,1), padding=(0,0))
            self.conv_dw  = Conv_block(mid_c, mid_c, kernel=(3,3), stride=stride, padding=(1,1), groups=mid_c)
            self.project  = Linear_block(mid_c, out_c, kernel=(1,1), stride=(1,1), padding=(0,0))
            self.residual = residual
        def forward(self, x):
            short = x
            x = self.project(self.conv_dw(self.conv(x)))
            return x + short if self.residual else x

    def read_dw(prefix, stride=(2,2), residual=False):
        in_c  = sd[f'{prefix}.conv.conv.weight'].shape[1]
        mid_c = sd[f'{prefix}.conv.conv.weight'].shape[0]
        out_c = sd[f'{prefix}.project.conv.weight'].shape[0]
        return Depth_Wise(in_c, mid_c, out_c, stride=stride, residual=residual)

    def read_residual_block(prefix):
        in_c  = sd[f'{prefix}.conv.conv.weight'].shape[1]
        mid_c = sd[f'{prefix}.conv.conv.weight'].shape[0]
        out_c = sd[f'{prefix}.project.conv.weight'].shape[0]
        return Depth_Wise(in_c, mid_c, out_c, stride=(1,1), residual=True)

    class ResidualGroup(nn.Module):
        def __init__(self, blocks):
            super().__init__()
            self.model = nn.Sequential(*blocks)
        def forward(self, x):
            return self.model(x)

    def count_residual_blocks(group_prefix):
        count = 0
        while f'{group_prefix}.model.{count}.conv.conv.weight' in sd:
            count += 1
        return count

    # conv1: Conv_block(3, 32, 3x3, stride 2)
    c1_out = sd['conv1.conv.weight'].shape[0]
    c1_in  = sd['conv1.conv.weight'].shape[1]

    # conv2_dw: depthwise Conv_block
    c2_out = sd['conv2_dw.conv.weight'].shape[0]

    # conv_6_sep
    c6s_in  = sd['conv_6_sep.conv.weight'].shape[1]
    c6s_out = sd['conv_6_sep.conv.weight'].shape[0]

    # conv_6_dw
    c6d_out = sd['conv_6_dw.conv.weight'].shape[0]
    c6d_k   = sd['conv_6_dw.conv.weight'].shape[2]

    # linear
    emb_in  = sd['linear.weight'].shape[1]
    emb_out = sd['linear.weight'].shape[0]

    # prob
    num_cls = sd['prob.weight'].shape[0]

    class MiniFASNetV2(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1     = Conv_block(c1_in, c1_out, kernel=(3,3), stride=(2,2), padding=(1,1))
            self.conv2_dw  = Conv_block(c2_out, c2_out, kernel=(3,3), stride=(1,1), padding=(1,1), groups=c2_out)
            self.conv_23   = read_dw('conv_23', stride=(2,2), residual=False)

            n3 = count_residual_blocks('conv_3')
            self.conv_3    = ResidualGroup([read_residual_block(f'conv_3.model.{i}') for i in range(n3)])

            self.conv_34   = read_dw('conv_34', stride=(2,2), residual=False)

            n4 = count_residual_blocks('conv_4')
            self.conv_4    = ResidualGroup([read_residual_block(f'conv_4.model.{i}') for i in range(n4)])

            self.conv_45   = read_dw('conv_45', stride=(2,2), residual=False)

            n5 = count_residual_blocks('conv_5')
            self.conv_5    = ResidualGroup([read_residual_block(f'conv_5.model.{i}') for i in range(n5)])

            self.conv_6_sep = Conv_block(c6s_in, c6s_out, kernel=(1,1), stride=(1,1), padding=(0,0))
            self.conv_6_dw  = Linear_block(c6d_out, c6d_out, kernel=(c6d_k, c6d_k), stride=(1,1), padding=(0,0), groups=c6d_out)
            self.conv_6_flatten = nn.Flatten()
            self.linear = nn.Linear(emb_in, emb_out, bias=False)
            self.bn     = nn.BatchNorm1d(emb_out)
            self.drop   = nn.Dropout()
            self.prob   = nn.Linear(emb_out, num_cls, bias=False)

        def forward(self, x):
            x = self.conv1(x)
            x = self.conv2_dw(x)
            x = self.conv_23(x)
            x = self.conv_3(x)
            x = self.conv_34(x)
            x = self.conv_4(x)
            x = self.conv_45(x)
            x = self.conv_5(x)
            x = self.conv_6_sep(x)
            x = self.conv_6_dw(x)
            x = self.conv_6_flatten(x)
            x = self.linear(x)
            x = self.bn(x)
            x = self.drop(x)
            x = self.prob(x)
            return x

    model = MiniFASNetV2()
    model.eval()
    missing, unexpected = model.load_state_dict(sd, strict=False)
    if missing:
        print(f"Missing keys ({len(missing)}): {missing[:3]}")
    if unexpected:
        print(f"Unexpected keys ({len(unexpected)}): {unexpected[:3]}")
    if not missing and not unexpected:
        print("Weights loaded: exact match.")

    os.makedirs('models', exist_ok=True)
    dummy = torch.randn(1, 3, 80, 80)
    with torch.no_grad():
        out = model(dummy)
        print(f"Forward pass OK. Output shape: {out.shape}")

    # Use legacy ONNX export to avoid torch.dynamo/onnxscript path
    torch.onnx.export(
        model, dummy, dst,
        input_names=['input'],
        output_names=['output'],
        opset_version=17,
        do_constant_folding=True,
        dynamo=False,
    )
    print(f"\nExported to: {dst}")
    print("Liveness detection enabled. Restart the server.")


if __name__ == '__main__':
    main()
