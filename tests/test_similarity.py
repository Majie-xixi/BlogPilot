import unittest

from blogpost.similarity import text_similarity, title_similarity


class SimilarityTests(unittest.TestCase):
    def test_same_title_is_identical(self):
        self.assertEqual(title_similarity("AI Agent 实战", "AI-Agent实战"), 1.0)

    def test_unrelated_text_is_lower_than_reworded_text(self):
        source = "大模型通过工具调用连接外部系统并执行任务"
        reworded = "大模型借助工具调用接入外部系统完成任务"
        unrelated = "家庭服务器使用硬盘阵列保存照片"
        self.assertGreater(text_similarity(source, reworded), text_similarity(source, unrelated))
