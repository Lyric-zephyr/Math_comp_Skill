-- 练习的难度标签不缩进；识别套题与解析标题，通知 LaTeX 模板居中排版。
function Pandoc(document)
  local practice = false
  document = document:walk({
    Header = function(heading)
      local text = pandoc.utils.stringify(heading.content)
      if heading.level == 2 and (text:match("^第%s*[12]%s*组") or text:match("^第%s*[12]%s*套")
          or text:match("^第一组") or text:match("^第二组")
          or text:match("^第一套") or text:match("^第二套")
          or text:match("^答案") or text:match("^参考答案")
          or text:match("^详细解析")) then
        practice = true
      end
    end,
    Para = function(paragraph)
      local text = pandoc.utils.stringify(paragraph.content)
      if text:match("^【难度：.+】$") or text:match("^【难度:.+】$") then
        paragraph.content:insert(1, pandoc.RawInline("latex", "\\noindent "))
        return paragraph
      end
    end,
  })
  if practice then document.meta.practice = true end
  return document
end
