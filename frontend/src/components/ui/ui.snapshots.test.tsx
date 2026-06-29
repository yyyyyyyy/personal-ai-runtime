import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import Badge from "./Badge";
import Button from "./Button";
import Card from "./Card";
import EmptyState from "./EmptyState";

describe("UI component snapshots", () => {
  it("Button primary", () => {
    const { container } = render(<Button>保存</Button>);
    expect(container.firstChild).toMatchSnapshot();
  });

  it("Button danger sm", () => {
    const { container } = render(
      <Button variant="danger" size="sm">
        删除
      </Button>
    );
    expect(container.firstChild).toMatchSnapshot();
  });

  it("Card", () => {
    const { container } = render(
      <Card>
        <p>内容</p>
      </Card>
    );
    expect(container.firstChild).toMatchSnapshot();
  });

  it("Badge tones", () => {
    const { container } = render(
      <div>
        <Badge>默认</Badge>
        <Badge tone="success">成功</Badge>
        <Badge tone="warning">警告</Badge>
      </div>
    );
    expect(container.firstChild).toMatchSnapshot();
  });

  it("EmptyState", () => {
    const { container } = render(
      <EmptyState
        title="暂无数据"
        description="创建第一个目标开始使用"
        action={<Button>新建</Button>}
      />
    );
    expect(container.firstChild).toMatchSnapshot();
  });
});
