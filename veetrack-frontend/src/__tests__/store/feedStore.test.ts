import { useFeedStore } from "@/store/feedStore";

const TOTAL = 8;

beforeEach(() => {
  useFeedStore.setState({ currentStoryIndex: 0, currentPage: 1 });
});

describe("feedStore — nextStory", () => {
  it("advances the story index", () => {
    useFeedStore.getState().nextStory(TOTAL);
    expect(useFeedStore.getState().currentStoryIndex).toBe(1);
  });

  it("clamps at last story index", () => {
    useFeedStore.setState({ currentStoryIndex: TOTAL - 1 });
    useFeedStore.getState().nextStory(TOTAL);
    expect(useFeedStore.getState().currentStoryIndex).toBe(TOTAL - 1);
  });

  it("resets currentPage to 1 when changing story", () => {
    useFeedStore.setState({ currentPage: 3 });
    useFeedStore.getState().nextStory(TOTAL);
    expect(useFeedStore.getState().currentPage).toBe(1);
  });
});

describe("feedStore — prevStory", () => {
  it("decrements the story index", () => {
    useFeedStore.setState({ currentStoryIndex: 3 });
    useFeedStore.getState().prevStory();
    expect(useFeedStore.getState().currentStoryIndex).toBe(2);
  });

  it("clamps at 0", () => {
    useFeedStore.getState().prevStory();
    expect(useFeedStore.getState().currentStoryIndex).toBe(0);
  });

  it("resets currentPage to 1", () => {
    useFeedStore.setState({ currentStoryIndex: 2, currentPage: 4 });
    useFeedStore.getState().prevStory();
    expect(useFeedStore.getState().currentPage).toBe(1);
  });
});

describe("feedStore — nextPage", () => {
  it("advances the page", () => {
    useFeedStore.setState({ currentPage: 2 });
    useFeedStore.getState().nextPage();
    expect(useFeedStore.getState().currentPage).toBe(3);
  });

  it("clamps at page 4", () => {
    useFeedStore.setState({ currentPage: 4 });
    useFeedStore.getState().nextPage();
    expect(useFeedStore.getState().currentPage).toBe(4);
  });
});

describe("feedStore — prevPage", () => {
  it("decrements the page", () => {
    useFeedStore.setState({ currentPage: 3 });
    useFeedStore.getState().prevPage();
    expect(useFeedStore.getState().currentPage).toBe(2);
  });

  it("clamps at page 1", () => {
    useFeedStore.getState().prevPage();
    expect(useFeedStore.getState().currentPage).toBe(1);
  });
});

describe("feedStore — goToPage / goToStory", () => {
  it("goToPage sets the page directly", () => {
    useFeedStore.getState().goToPage(4);
    expect(useFeedStore.getState().currentPage).toBe(4);
  });

  it("goToStory sets the index and resets page to 1", () => {
    useFeedStore.setState({ currentPage: 3 });
    useFeedStore.getState().goToStory(5);
    expect(useFeedStore.getState().currentStoryIndex).toBe(5);
    expect(useFeedStore.getState().currentPage).toBe(1);
  });
});
